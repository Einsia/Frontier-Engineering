"""Isolation regressions for the three StructuralOptimization benchmarks.

What was actually wrong
-----------------------
Unlike most of the converted benchmarks, these three never ``exec_module``'d the
candidate into the scoring process -- all three already ran it as a subprocess
and rescored the returned design themselves. The holes were subtler:

``ISCSO2015`` / ``ISCSO2023``
    ``build_fem_and_evaluate()`` imported the FEM solver *lazily*, inside the
    function, i.e. **after** the candidate subprocess had returned. The
    candidate runs under the same uid as the scorer and therefore owns the
    sandbox files, so it can ``chmod`` the harness's read-only bit back off and
    rewrite ``verification/fem_truss2d.py``. The scorer then imported the
    candidate's solver and reported whatever weight it liked. This is
    ``candidate_sandbox``'s invariant 1.

``ISCSO2015`` / ``TopologyOptimization``
    The subprocess return code was recorded into ``metrics`` and then ignored;
    a candidate that wrote ``submission.json`` and crashed was still scored.
    This is invariant 3 (``TopologyOptimization`` is where that invariant came
    from).

``ISCSO2023``
    ``_wrap()`` imported ``openevolve`` unguarded, so on a host without it every
    run -- honest or not -- raised out of ``evaluate()`` and scored INVALID. It
    also failed any run that wrote a single byte to stderr, which kills an
    honest submission over a numpy warning.

The exploits below are re-implemented from reading the archived programs and
the pre-fix evaluator sources. Nothing under ``baseline_archive/`` is executed.

These drive each benchmark's own ``frontier_eval/run_eval.py`` inside a sandbox
copy that reproduces what the unified harness does (copy the benchmark, drop the
write bit on the readonly paths, export ``FRONTIER_ENGINEERING_ROOT``).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "benchmarks" / "StructuralOptimization"
TASKS = ("ISCSO2015", "ISCSO2023", "TopologyOptimization")

INVALID_COMBINED_SCORE = -1e18

# combined_score produced by each task's shipped scripts/init.py. The FEM is
# deterministic, so the hardened evaluator must reproduce these bit for bit.
PUBLISHED_SCORE = {
    "ISCSO2015": -5401.589001522704,
    "ISCSO2023": -77813242.90462679,
    "TopologyOptimization": -195.9152621065792,
}

SOLUTION_KEY = {
    "ISCSO2015": "solution_vector",
    "ISCSO2023": "solution_vector",
    "TopologyOptimization": "density_vector",
}

# The solver file the pre-fix evaluator imported only after the candidate ran.
# TopologyOptimization is absent on purpose: its FEM lives inside
# verification/evaluator.py, which was already loaded before the candidate ran,
# so it never had this hole.
LATE_IMPORTED_SOLVER = {
    "ISCSO2015": "fem_truss2d.py",
    "ISCSO2023": "fem_truss3d.py",
}
READONLY_RELS = ("references", "verification", "frontier_eval")


# --------------------------------------------------------------------------
# Harness reproduction
# --------------------------------------------------------------------------


def _drop_write_bit(root: Path) -> None:
    """What ``_enforce_readonly`` in the unified evaluator does."""
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    for rel in READONLY_RELS:
        target = root / rel
        if not target.exists():
            continue
        entries = sorted(target.rglob("*"), reverse=True) if target.is_dir() else []
        for path in [*entries, target]:
            try:
                path.chmod(stat.S_IMODE(path.stat().st_mode) & ~write_bits)
            except OSError:
                pass


def _restore_write_bit(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        try:
            path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR)
        except OSError:
            pass


class Sandbox:
    """A throwaway copy of one benchmark, staged the way the harness stages it."""

    def __init__(self, task: str, tmp_path: Path) -> None:
        self.task = task
        self.root = tmp_path / task
        shutil.copytree(BENCH_ROOT / task, self.root)
        self.candidate = self.root / "scripts" / "init.py"
        self.honest_source = self.candidate.read_text(encoding="utf-8")

    def stage_exploit(self, tail: str, **subs: str) -> None:
        """Append misbehaviour after the honest program has done its job.

        The candidate is copied into a scratch directory before it runs, so it
        cannot pull in a second file from the benchmark tree; the honest source
        has to be part of the same file.
        """
        for key, value in subs.items():
            tail = tail.replace(f"__{key}__", value)
        self.candidate.write_text(
            self.honest_source + "\n\n# --- exploit ---\n" + tail, encoding="utf-8"
        )

    def run(self, extra_env: dict[str, str] | None = None) -> tuple[dict, dict]:
        _drop_write_bit(self.root)
        metrics_out = self.root / "metrics.json"
        artifacts_out = self.root / "artifacts.json"
        env = dict(os.environ)
        # The harness points this at the real repo, so the scorer loads its
        # problem data from the pristine tree rather than the sandbox copy.
        env["FRONTIER_ENGINEERING_ROOT"] = str(REPO_ROOT)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.update(extra_env or {})
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(self.root / "frontier_eval" / "run_eval.py"),
                    "--candidate", str(self.candidate),
                    "--metrics-out", str(metrics_out),
                    "--artifacts-out", str(artifacts_out),
                ],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=1800,
                env=env,
            )
        finally:
            _restore_write_bit(self.root)
        assert proc.returncode == 0, f"run_eval crashed:\n{proc.stderr[-4000:]}"
        return (
            json.loads(metrics_out.read_text(encoding="utf-8")),
            json.loads(artifacts_out.read_text(encoding="utf-8")),
        )


@pytest.fixture()
def sandbox_factory(tmp_path):
    made: list[Sandbox] = []

    def _make(task: str) -> Sandbox:
        box = Sandbox(task, tmp_path)
        made.append(box)
        return box

    yield _make
    # pytest cannot clean a tree whose directories lost their write bit.
    for box in made:
        _restore_write_bit(box.root)


# --------------------------------------------------------------------------
# Exploit tails (appended after the honest program's main() has run)
# --------------------------------------------------------------------------

CRASH_AFTER_SUBMISSION = """
import os as _os
import sys as _sys

print("submission written, now crashing on purpose")
_sys.stdout.flush()
_os._exit(1)
"""

# Appends a class override to the scorer's own solver module. Appending rather
# than replacing keeps helpers such as generate_tower_topology intact, which is
# what a real attacker would do.
HIJACK_SOLVER = '''
import json as _json
import os as _os
import pathlib as _pathlib

_OVERRIDE = """

# --- appended by the candidate ---
import numpy as _np


class TrussFEM2D:
    def __init__(self, nodes, elements, E, supports):
        self.n_elements = len(elements)
        self.n_dofs = 2 * len(nodes)

    def solve(self, areas, forces):
        return (
            _np.zeros(self.n_dofs),
            _np.zeros(self.n_elements),
            _np.ones(self.n_elements),
        )

    def compute_weight(self, areas, rho):
        return 1.0


class TrussFEM3D:
    def __init__(self, nodes, elements, E, supports):
        self.n_elements = len(elements)
        self.n_dofs = 3 * len(nodes)

    def solve(self, areas, forces):
        return _np.zeros(self.n_dofs), _np.zeros(self.n_elements)

    def compute_weight(self, areas, rho):
        return 1.0
"""

_reached = []
_roots = [_pathlib.Path(__file__).resolve().parents[1]]
_extra = _os.environ.get("FE_SANDBOX_ROOT")
if _extra:
    _roots.append(_pathlib.Path(_extra))
for _base in _roots:
    _target = _base / "verification" / "__SOLVER__"
    if not _target.is_file():
        continue
    try:
        # The harness dropped the write bit, but we own the file.
        _os.chmod(_target.parent, 0o755)
        _os.chmod(_target, 0o644)
        _target.write_text(_target.read_text() + _OVERRIDE)
        _reached.append(str(_target))
    except OSError as _exc:
        print("HIJACK_BLOCKED", _exc)
print("HIJACK_WROTE " + _json.dumps(_reached))
'''

SELF_REPORT_LIES = """
import json as _json
import pathlib as _pathlib

_path = _pathlib.Path("temp/submission.json")
_sub = _json.loads(_path.read_text())
_sub.update({
    "weight": 1.0,
    "weight_kg": 1.0,
    "compliance": 1e-9,
    "volume_fraction": 0.0,
    "max_stress": 0.0,
    "max_stress_violation": 0.0,
    "max_displacement_violation": 0.0,
    "feasible": True,
    "score": 1.0,
    "combined_score": 1e9,
    "objective": 1.0,
    "valid": 1.0,
})
_path.write_text(_json.dumps(_sub))
print("self-reported fields injected")
"""

UNDERREPORT_BUDGET = """
import json as _json
import pathlib as _pathlib

_path = _pathlib.Path("temp/submission.json")
_sub = _json.loads(_path.read_text())
_sub["num_evaluations"] = 1
_path.write_text(_json.dumps(_sub))
"""

PROBE_FILESYSTEM = """
import json as _json
import pathlib as _pathlib

_base = _pathlib.Path(__file__).resolve().parents[1]
print("PROBE " + _json.dumps({
    "cwd": str(_pathlib.Path.cwd()),
    "file_parent": str(_pathlib.Path(__file__).resolve().parent),
    "verification_visible": (_base / "verification").is_dir(),
    "references_visible": (_base / "references").is_dir(),
    "frontier_eval_visible": (_base / "frontier_eval").is_dir(),
}))
"""


def _stdout_line(artifacts: dict, prefix: str) -> str | None:
    for line in artifacts.get("program_stdout", "").splitlines():
        if line.startswith(prefix):
            return line
    return None


# --------------------------------------------------------------------------
# 1. Honest runs must not move by a single bit
# --------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("task", TASKS)
def test_honest_score_unchanged(task, sandbox_factory):
    box = sandbox_factory(task)
    metrics, _ = box.run()
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == PUBLISHED_SCORE[task], (
        f"{task}: honest score moved from {PUBLISHED_SCORE[task]!r} "
        f"to {metrics['combined_score']!r}"
    )


# --------------------------------------------------------------------------
# 2. Invariant 1 -- the scorer's FEM solver cannot be swapped out
# --------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("task", sorted(LATE_IMPORTED_SOLVER))
def test_solver_hijack_does_not_change_the_score(task, sandbox_factory):
    box = sandbox_factory(task)
    solver = box.root / "verification" / LATE_IMPORTED_SOLVER[task]
    original = solver.read_text(encoding="utf-8")
    box.stage_exploit(HIJACK_SOLVER, SOLVER=LATE_IMPORTED_SOLVER[task])
    # Hand the attacker the sandbox path outright. Running the candidate from a
    # scratch copy already hides it from __file__, but candidate_sandbox is
    # explicit that a same-uid child can still recover the scorer's cwd via
    # /proc/<ppid>/cwd. Granting the path here isolates the variable under test:
    # what defeats the hijack is *when* the solver is imported, not whether the
    # candidate can find it.
    metrics, artifacts = box.run(extra_env={"FE_SANDBOX_ROOT": str(box.root)})

    assert solver.read_text(encoding="utf-8") != original, (
        "the candidate did not manage to rewrite the solver, so this run does "
        "not exercise the hijack"
    )
    # The design handed over is the honest one, so the honest score is the
    # correct answer. A forged solver reports weight 1.0 -> combined_score -1.0.
    assert metrics["combined_score"] == PUBLISHED_SCORE[task]
    assert metrics["combined_score"] != -1.0
    assert metrics.get("weight_kg") != 1.0


@pytest.mark.slow
@pytest.mark.parametrize("task", sorted(LATE_IMPORTED_SOLVER))
def test_late_import_would_have_been_exploitable(task, sandbox_factory):
    """Pin the premise: import *ordering* is what closes this, not the chmod.

    The harness drops the write bit on ``verification/`` before the run, but the
    candidate owns those files, so ``chmod`` puts it back. Only binding the
    solver before the candidate runs actually helps.
    """
    box = sandbox_factory(task)
    solver = box.root / "verification" / LATE_IMPORTED_SOLVER[task]
    original = solver.read_text(encoding="utf-8")

    box.stage_exploit(HIJACK_SOLVER, SOLVER=LATE_IMPORTED_SOLVER[task])
    _metrics, artifacts = box.run(extra_env={"FE_SANDBOX_ROOT": str(box.root)})

    # The write bit alone did not stop it.
    assert _stdout_line(artifacts, "HIJACK_BLOCKED") is None
    tampered = solver.read_text(encoding="utf-8")
    assert tampered != original, (
        "premise broken: the candidate could not rewrite the solver at all, so "
        "this test no longer demonstrates anything"
    )
    assert "appended by the candidate" in tampered

    # Reading the scorer off disk *after* the candidate ran -- what the pre-fix
    # code did with its function-local `from fem_truss2d import ...` -- picks up
    # the forged solver and mints the candidate's number.
    submission = json.loads(artifacts["submission.json"])
    forged = _score_with_late_loaded_scorer(box, task, submission)
    assert forged["objective"] == 1.0, forged
    assert forged["feasible"] is True, forged
    assert -forged["objective"] != PUBLISHED_SCORE[task]


def _score_with_late_loaded_scorer(box: Sandbox, task: str, submission: dict) -> dict:
    """Reproduce the pre-fix ordering: read the solver off disk after the run."""
    problem = json.loads(
        (BENCH_ROOT / task / "references" / "problem_data.json").read_text(encoding="utf-8")
    )
    mod_name = f"_late_loaded_{task}"
    for name in ("fem_truss2d", "fem_truss3d", mod_name):
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(
        mod_name, box.root / "verification" / "evaluator.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    saved_path = list(sys.path)
    saved_root = os.environ.get("FRONTIER_ENGINEERING_ROOT")
    os.environ["FRONTIER_ENGINEERING_ROOT"] = str(REPO_ROOT)
    try:
        spec.loader.exec_module(module)
        return module.build_fem_and_evaluate(
            submission[SOLUTION_KEY[task]], problem
        )
    finally:
        if saved_root is None:
            os.environ.pop("FRONTIER_ENGINEERING_ROOT", None)
        else:
            os.environ["FRONTIER_ENGINEERING_ROOT"] = saved_root
        sys.path[:] = saved_path
        for name in ("fem_truss2d", "fem_truss3d", mod_name):
            sys.modules.pop(name, None)


# --------------------------------------------------------------------------
# 3. Invariant 3 -- a crash is a failure even with a good submission on disk
# --------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("task", TASKS)
def test_nonzero_returncode_rejects_the_run(task, sandbox_factory):
    box = sandbox_factory(task)
    box.stage_exploit(CRASH_AFTER_SUBMISSION)
    metrics, artifacts = box.run()

    assert metrics["program_returncode"] == 1.0
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == INVALID_COMBINED_SCORE
    # The return code is the only reason this run was rejected: the submission
    # itself was written and was perfectly well-formed.
    assert "non-zero" in artifacts.get("error_message", "")


# --------------------------------------------------------------------------
# 4. Invariant 2 -- nothing the candidate says about its own design is used
# --------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("task", TASKS)
def test_self_reported_metrics_are_ignored(task, sandbox_factory):
    box = sandbox_factory(task)
    box.stage_exploit(SELF_REPORT_LIES)
    metrics, artifacts = box.run()

    assert metrics["combined_score"] == PUBLISHED_SCORE[task], (
        "a self-reported field leaked into the score"
    )
    ignored = artifacts.get("ignored_submission_fields", "")
    for field in ("combined_score", "feasible", "objective", "valid"):
        assert field in ignored, f"{field} not listed as ignored: {ignored!r}"


# --------------------------------------------------------------------------
# 5. Residual risk, pinned rather than hidden
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_num_evaluations_remains_unverifiable(sandbox_factory):
    """ISCSO2023's evaluation budget is self-reported and cannot be checked.

    This asserts the *status quo* on purpose: a candidate that under-reports
    still passes the gate. What the fix guarantees is only that the evaluator
    says so out loud instead of implying the budget was enforced.
    """
    box = sandbox_factory("ISCSO2023")
    box.stage_exploit(UNDERREPORT_BUDGET)
    metrics, artifacts = box.run()

    assert metrics["valid"] == 1.0
    assert artifacts["num_evaluations_reported"] == "1"
    assert artifacts["num_evaluations_status"] == "unverified"
    assert metrics["num_evaluations_verified"] == 0.0


@pytest.mark.slow
@pytest.mark.parametrize("task", TASKS)
def test_candidate_cannot_see_the_benchmark_tree(task, sandbox_factory):
    """The candidate runs from a scratch copy, so __file__ is not a way in."""
    box = sandbox_factory(task)
    box.stage_exploit(PROBE_FILESYSTEM)
    _metrics, artifacts = box.run()

    line = _stdout_line(artifacts, "PROBE ")
    assert line, artifacts.get("program_stdout", "")
    probe = json.loads(line[len("PROBE "):])
    assert probe["verification_visible"] is False, probe
    assert probe["frontier_eval_visible"] is False, probe
    assert str(box.root) not in probe["file_parent"], probe
