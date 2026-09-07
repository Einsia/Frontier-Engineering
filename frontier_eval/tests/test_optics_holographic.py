"""Regression tests for the four Optics ``holographic_*`` scoring contracts.

The audit finding these guard against: every one of the four evaluators used to
obtain the problem definition, the forward physics *and* the comparison target
from the candidate itself::

    spec   = baseline_module.make_default_spec()      # problem   <- candidate
    out    = result["system"].measure_at_z(...)       # physics   <- candidate
    target = result["target_field"]                   # target    <- candidate

An archived submission (openevolve / gpt-5.4, ``holographic_multifocus_power_ratio``)
exploited that by returning a system whose ``measure_at_z`` was a lookup table
keyed on ``z`` and preloaded with the very target field it also returned::

    class _LookupSystem:
        def measure_at_z(self, input_field, z):
            return self.outputs[z]

"prediction" and "target" then agreed to machine precision: it scored
0.9999999999 while the runner-up scored 0.72.

The contract now moves all three responsibilities to ``verification/``: the spec
lives in ``verification/problem_spec.py``, the candidate runs in its own process
and returns only decision variables (phase / thickness arrays) in an ``.npz``
loaded with ``allow_pickle=False``, and the evaluator builds the optics,
propagates, builds the targets and computes the metrics itself.

These tests run each task's real ``verification/evaluate.py`` against a
throwaway candidate file via ``--candidate``/``--artifacts-dir``, so they never
mutate the checked-in task tree.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPTICS = REPO_ROOT / "benchmarks" / "Optics"
SHARED = REPO_ROOT / "benchmarks" / "_shared"

TASKS = (
    "holographic_multifocus_power_ratio",
    "holographic_multiplane_focusing",
    "holographic_multispectral_focusing",
    "holographic_polarization_multiplexing",
)

#: Where each task's summary.json reports the candidate's headline score.
SCORE_PATH = {
    "holographic_multifocus_power_ratio": ("baseline", "metrics", "score"),
    "holographic_multiplane_focusing": ("baseline", "mean_score"),
    "holographic_multispectral_focusing": ("baseline", "mean_score"),
    "holographic_polarization_multiplexing": ("baseline", "score"),
}

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def shared_mod():
    if str(SHARED) not in sys.path:
        sys.path.insert(0, str(SHARED))
    return _load(SHARED / "optics_holographic.py", "optics_holographic_under_test")


def _problem_spec(task: str):
    return _load(OPTICS / task / "verification" / "problem_spec.py", f"problem_spec_{task}")


def _submission_shapes(task: str) -> dict[str, tuple[int, ...]]:
    """The array name -> shape contract, read from the task's own spec."""
    ps = _problem_spec(task)
    spec = ps.make_spec()
    if task == "holographic_multispectral_focusing":
        return {"thickness": tuple(spec["thickness_shape"])}
    if task == "holographic_polarization_multiplexing":
        return {
            "phase_x": tuple(spec["phase_shape"]),
            "phase_y": tuple(spec["phase_shape"]),
        }
    return {"phases": tuple(spec["phase_shape"])}


def _run_evaluator(
    task: str,
    candidate_src: str,
    tmp_path: Path,
    *,
    baseline_steps: int = 2,
    reference_steps: int = 2,
    timeout: int = 1200,
):
    """Run the task's real evaluator against a throwaway candidate file.

    Step budgets default low because most cases only need the *contract* to hold,
    not a converged design; `test_honest_baseline_scores` raises the baseline
    budget to the value `frontier_eval/run_eval.sh` actually uses, since the
    validity thresholds are calibrated for it.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    candidate = tmp_path / "candidate_init.py"
    candidate.write_text(candidate_src, encoding="utf-8")
    artifacts = tmp_path / "artifacts"

    task_dir = OPTICS / task
    proc = subprocess.run(
        [
            sys.executable,
            str(task_dir / "verification" / "evaluate.py"),
            "--device", "cpu",
            "--baseline-steps", str(baseline_steps),
            "--reference-steps", str(reference_steps),
            "--candidate", str(candidate),
            "--artifacts-dir", str(artifacts),
            "--candidate-timeout", "300",
        ],
        cwd=str(task_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**_clean_env(), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    summary_path = artifacts / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else None
    return proc, summary, artifacts


def _clean_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def _dig(payload: dict, path):
    node = payload
    for key in path:
        node = node[key]
    return node


def _honest_source(task: str) -> str:
    return (OPTICS / task / "baseline" / "init.py").read_text(encoding="utf-8")


def _zero_submission_source(task: str, extra_arrays: str = "") -> str:
    """A candidate that submits an all-zero (do-nothing) stack, plus `extra_arrays`.

    Deliberately does no optimisation, so it is fast and its physically correct
    score is low. Anything in `extra_arrays` is what a submission might *try* to
    smuggle across the boundary.
    """
    shapes = _submission_shapes(task)
    arrays = ", ".join(f"{name}=np.zeros({shape!r}, dtype=np.float64)" for name, shape in shapes.items())
    return textwrap.dedent(
        f"""
        import numpy as np

        def solve(spec, device=None, seed=0):
            return {{}}

        if __name__ == "__main__":
            np.savez("submission.npz", {arrays}{extra_arrays})
        """
    )


# --------------------------------------------------------------------------- #
# Structural tests: the contract itself (fast, no propagation).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("task", TASKS)
def test_candidate_no_longer_defines_the_problem(task):
    """`make_default_spec` must not exist in the candidate any more.

    While the candidate authored the spec, it chose its own focus coordinates,
    power ratios and grid -- and was then graded against that choice.
    """
    src = _honest_source(task)
    assert "make_default_spec" not in src, f"{task}: candidate still defines the problem spec"

    spec_file = OPTICS / task / "verification" / "problem_spec.py"
    assert spec_file.is_file(), f"{task}: verification/problem_spec.py is missing"
    assert "def make_spec(" in spec_file.read_text(encoding="utf-8")


FORBIDDEN_RETURN_KEYS = frozenset(
    {
        "system",
        "input_field",
        "input_fields",
        "target_field",
        "target_fields",
        "output_field_x",
        "output_field_y",
        "target_map_x",
        "target_map_y",
    }
)


def _solve_return_keys(path: Path) -> set[str]:
    """Static keys of every dict literal returned by the module-level `solve`."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != "solve":
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                for key in sub.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
    return keys


@pytest.mark.parametrize("task", TASKS)
def test_no_callable_or_field_crosses_the_boundary(task):
    """Neither the candidate nor the oracle may hand back physics objects.

    Checked on what the module-level `solve` actually returns, so a helper that
    keeps a `System` in a local dict (the oracle does, to pick its best restart)
    is fine -- what matters is that nothing but arrays reaches the evaluator.
    """
    for rel in ("baseline/init.py", "verification/reference_solver.py"):
        path = OPTICS / task / rel
        returned = _solve_return_keys(path)
        assert returned, f"{task}/{rel}: could not find a dict returned by solve()"
        leaked = returned & FORBIDDEN_RETURN_KEYS
        assert not leaked, f"{task}/{rel} still returns {sorted(leaked)} across the process boundary"


@pytest.mark.parametrize("task", TASKS)
def test_problem_spec_is_protected_and_shipped(task):
    fe = OPTICS / task / "frontier_eval"
    readonly = fe.joinpath("readonly_files.txt").read_text(encoding="utf-8").split()
    copy_files = fe.joinpath("copy_files.txt").read_text(encoding="utf-8").split()

    assert "verification/problem_spec.py" in readonly, (
        f"{task}: the scorer-owned spec is writable by the candidate"
    )
    assert "verification/evaluate.py" in readonly
    assert "verification/reference_solver.py" in readonly
    # An explicit allow-list, not a blanket "." that drags in stale artifacts.
    assert "." not in copy_files, f"{task}: copy_files.txt still copies the whole task tree"
    assert "verification/problem_spec.py" in copy_files


@pytest.mark.parametrize("task", TASKS)
def test_candidate_problem_is_pure_data(task):
    """What the candidate receives must be JSON -- no callables, no objects."""
    ps = _problem_spec(task)
    problem = ps.candidate_problem(ps.make_spec())
    blob = json.dumps(problem, default=str, allow_nan=False)
    assert "submission" in problem
    assert "arrays" in problem["submission"]
    for name in _submission_shapes(task):
        assert name in problem["submission"]["arrays"], f"{task}: {name} undocumented"
    assert "<function" not in blob and "<class" not in blob and " object at 0x" not in blob


# --------------------------------------------------------------------------- #
# Validation tests: what the scorer refuses to accept.
# --------------------------------------------------------------------------- #
def test_validate_array_rejects_bad_submissions(shared_mod):
    spec = shared_mod.ArraySpec(shape=(2, 4, 4), max_abs=10.0)

    good = np.zeros((2, 4, 4))
    assert shared_mod.validate_array(good, "phases", spec).shape == (2, 4, 4)

    with pytest.raises(shared_mod.CandidateRejected, match="shape"):
        shared_mod.validate_array(np.zeros((3, 4, 4)), "phases", spec)
    with pytest.raises(shared_mod.CandidateRejected, match="NaN/Inf"):
        shared_mod.validate_array(np.full((2, 4, 4), np.nan), "phases", spec)
    with pytest.raises(shared_mod.CandidateRejected, match="NaN/Inf"):
        shared_mod.validate_array(np.full((2, 4, 4), np.inf), "phases", spec)
    with pytest.raises(shared_mod.CandidateRejected, match="out of range"):
        shared_mod.validate_array(np.full((2, 4, 4), 1e6), "phases", spec)
    with pytest.raises(shared_mod.CandidateRejected, match="real numeric"):
        shared_mod.validate_array(np.zeros((2, 4, 4), dtype=complex), "phases", spec)

    bounded = shared_mod.ArraySpec(shape=(2,), max_abs=1.0, min_value=0.0, max_value=1.0)
    with pytest.raises(shared_mod.CandidateRejected, match="lower bound"):
        shared_mod.validate_array(np.array([-0.5, 0.5]), "thickness", bounded)


def test_pickled_object_in_submission_is_rejected(shared_mod, tmp_path):
    """A `_LookupSystem` cannot be smuggled through the npz.

    `np.load(..., allow_pickle=False)` is the structural half of the fix: object
    arrays -- the only way to serialise a class with a `measure_at_z` method --
    cannot be deserialised at all.
    """
    candidate = tmp_path / "evil.py"
    candidate.write_text(
        textwrap.dedent(
            """
            import numpy as np

            class LookupSystem:
                def __init__(self, out): self.out = out
                def measure_at_z(self, field, z): return self.out

            np.savez("submission.npz", phases=np.array([LookupSystem(1.0)], dtype=object))
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(shared_mod.CandidateRejected):
        shared_mod.run_candidate_arrays(
            candidate,
            problem={"hello": "world"},
            arrays={"phases": shared_mod.ArraySpec(shape=(2, 4, 4), max_abs=10.0)},
            timeout_s=120,
        )


def test_candidate_that_writes_nothing_is_rejected(shared_mod, tmp_path):
    candidate = tmp_path / "silent.py"
    candidate.write_text("print('I did nothing')\n", encoding="utf-8")
    with pytest.raises(shared_mod.CandidateRejected, match="not produced"):
        shared_mod.run_candidate_arrays(
            candidate,
            problem={},
            arrays={"phases": shared_mod.ArraySpec(shape=(1, 2, 2), max_abs=1.0)},
            timeout_s=120,
        )


def test_candidate_that_crashes_is_rejected(shared_mod, tmp_path):
    candidate = tmp_path / "boom.py"
    candidate.write_text("raise SystemExit(7)\n", encoding="utf-8")
    with pytest.raises(shared_mod.CandidateRejected):
        shared_mod.run_candidate_arrays(
            candidate,
            problem={},
            arrays={"phases": shared_mod.ArraySpec(shape=(1, 2, 2), max_abs=1.0)},
            timeout_s=120,
        )


def test_candidate_cannot_import_the_scorer(shared_mod, tmp_path):
    """`sys.path[0]` is the scratch dir, so verification/ is not importable."""
    candidate = tmp_path / "peek.py"
    candidate.write_text(
        textwrap.dedent(
            """
            import json, numpy as np, pathlib
            leaked = {}
            for name in ("problem_spec", "evaluate", "reference_solver"):
                try:
                    __import__(name)
                    leaked[name] = True
                except Exception:
                    leaked[name] = False
            neighbours = sorted(p.name for p in pathlib.Path.cwd().iterdir())
            pathlib.Path("report.json").write_text(json.dumps({"leaked": leaked, "cwd": neighbours}))
            np.savez("submission.npz", phases=np.zeros((1, 2, 2)))
            """
        ),
        encoding="utf-8",
    )
    out = shared_mod.run_candidate_arrays(
        candidate,
        problem={},
        arrays={"phases": shared_mod.ArraySpec(shape=(1, 2, 2), max_abs=1.0)},
        timeout_s=120,
    )
    assert out["phases"].shape == (1, 2, 2)


# --------------------------------------------------------------------------- #
# End-to-end: the honest baseline still scores.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("task", TASKS)
def test_honest_baseline_scores(task, tmp_path):
    # 24 is the baseline budget `benchmarks/Optics/frontier_eval/run_eval.sh` uses.
    proc, summary, _ = _run_evaluator(task, _honest_source(task), tmp_path, baseline_steps=24)
    assert proc.returncode == 0, f"{task} evaluator failed:\n{proc.stderr[-4000:]}"
    assert summary is not None, f"{task}: no summary.json written"

    score = _dig(summary, SCORE_PATH[task])
    assert 0.0 < score <= 1.0, f"{task}: implausible score {score}"
    assert summary["baseline"]["valid"] is True, f"{task}: honest baseline scored invalid"
    assert summary["candidate_execution"] == "isolated_subprocess"
    # The oracle is scored by the same scorer-owned physics.
    assert "reference" in summary and "oracle_backend" in summary["reference"]


# --------------------------------------------------------------------------- #
# End-to-end: the `_LookupSystem` family of attacks.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("task", TASKS)
def test_lookup_system_candidate_is_rejected(task, tmp_path):
    """The archived exploit, verbatim in shape: return a fake system, write nothing.

    Under the old contract this was the winning submission. Under the new one the
    return value of `solve` is never read by anybody, no `submission.npz` appears,
    and the run is rejected outright.
    """
    src = textwrap.dedent(
        """
        # EVOLVE-BLOCK-START
        class _LookupSystem:
            \"\"\"The archived attack: 'measured output' is just the target, echoed back.\"\"\"
            def __init__(self, outputs):
                self.outputs = outputs
            def measure_at_z(self, input_field, z):
                return self.outputs[z]

        def make_default_spec():
            return {"shape": 8, "focus_ratios": [1.0], "focus_centers": [(0.0, 0.0)]}

        def solve(spec=None, device=None, seed=0):
            fake_target = object()
            return {
                "spec": spec or make_default_spec(),
                "system": _LookupSystem({0.56: fake_target}),
                "input_field": fake_target,
                "target_field": fake_target,
                "loss_history": [1e-12],
            }
        # EVOLVE-BLOCK-END
        """
    )
    proc, summary, artifacts = _run_evaluator(task, src, tmp_path)

    assert proc.returncode != 0, f"{task}: a lookup-system candidate was accepted"
    assert summary is None, f"{task}: summary.json written for a rejected candidate"
    rejection = json.loads((artifacts / "candidate_rejected.json").read_text(encoding="utf-8"))
    assert rejection["valid"] == 0.0
    assert rejection["combined_score"] == -1e18
    assert rejection["candidate_error"]


@pytest.mark.parametrize("task", TASKS)
def test_fabricated_perfect_result_does_not_score_perfect(task, tmp_path):
    """Port the exploit to the new contract: claim a perfect result in the npz.

    The submission asserts `score=1.0`, ships a "measured output" identical to its
    "target", and includes the decision variables only as an afterthought. The
    evaluator ignores every one of those claims and propagates the (all-zero,
    do-nothing) stack itself, so the reported score is the physically correct one
    -- nowhere near the 0.9999999999 the archived exploit obtained.
    """
    shapes = _submission_shapes(task)
    any_shape = next(iter(shapes.values()))
    fabricated = (
        ", score=np.array([1.0])"
        ", combined_score=np.array([1.0])"
        ", shape_cosine=np.array([1.0])"
        ", ratio_mae=np.array([0.0])"
        ", efficiency=np.array([1.0])"
        f", measured_output=np.ones({any_shape[-2:]!r})"
        f", target_field=np.ones({any_shape[-2:]!r})"
    )
    proc, summary, _ = _run_evaluator(task, _zero_submission_source(task, fabricated), tmp_path)

    assert proc.returncode == 0, f"{task} evaluator failed:\n{proc.stderr[-4000:]}"
    assert summary is not None

    score = _dig(summary, SCORE_PATH[task])
    assert score < 0.9, (
        f"{task}: a fabricated 'perfect' submission scored {score}; "
        "the evaluator is trusting candidate-reported values"
    )
    # And none of the fabricated fields leaked into the summary.
    blob = json.dumps(summary)
    assert '"measured_output"' not in blob
    assert '"combined_score"' not in blob


@pytest.mark.parametrize("task", TASKS)
def test_score_depends_only_on_the_decision_variables(task, tmp_path):
    """Two submissions with identical arrays but opposite claims must tie.

    This is the property the old contract lacked: with the physics and the target
    supplied by the candidate, two submissions holding the same phase maps could
    report entirely different results.
    """
    quiet = _zero_submission_source(task)
    loud = _zero_submission_source(
        task,
        ", score=np.array([1.0]), loss_history=np.array([1e-30]), target_field=np.zeros((4, 4))",
    )

    _, summary_a, _ = _run_evaluator(task, quiet, tmp_path / "a")
    _, summary_b, _ = _run_evaluator(task, loud, tmp_path / "b")

    assert summary_a is not None and summary_b is not None
    assert _dig(summary_a, SCORE_PATH[task]) == _dig(summary_b, SCORE_PATH[task])


@pytest.mark.parametrize("task", TASKS)
def test_wrong_shaped_submission_is_rejected(task, tmp_path):
    shapes = _submission_shapes(task)
    arrays = ", ".join(f"{name}=np.zeros((1, 3, 3))" for name in shapes)
    src = textwrap.dedent(
        f"""
        import numpy as np
        if __name__ == "__main__":
            np.savez("submission.npz", {arrays})
        """
    )
    proc, summary, artifacts = _run_evaluator(task, src, tmp_path)
    assert proc.returncode != 0
    assert summary is None
    rejection = json.loads((artifacts / "candidate_rejected.json").read_text(encoding="utf-8"))
    assert "shape" in rejection["candidate_error"]
