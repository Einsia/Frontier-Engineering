"""Candidate-isolation regressions for three Robotics parameter/trajectory benchmarks.

Covered here:

* ``Robotics/PIDTuning``
* ``Robotics/RobotArmCycleTimeOptimization``
* ``Robotics/QuadrupedGaitOptimization``

All three shipped the same defect: the candidate was already run as a
subprocess, but the scoring module -- and, for two of them, the graded instance
-- was fetched from ``FRONTIER_ENGINEERING_ROOT`` *after* the candidate had had
a turn on the same filesystem, with the whole environment passed straight
through to the child::

    proc = subprocess.run([sys.executable, sandbox_program], ...)   # candidate
    ...
    eval_path = (benchmark_dir / "verification" / "evaluator.py").resolve()
    spec.loader.exec_module(module)                                 # scorer
    raw_score = float(module.evaluate(sandbox_submission))

Measured against the pre-hardening files, on a scratch copy of the repository:

===============================  ==========================  ====================
attack                           before                      honest baseline
===============================  ==========================  ====================
PID: rewrite verification/        999.0                       0.036626766599899996
PID: rewrite pid_config.json      11683.569318244708          0.036626766599899996
ARM: rewrite verification/        1.0 (ceiling of 1/(1+T))    0.2921925682511491
ARM: rewrite kuka model.urdf      0.0 (suppression)           0.2921925682511491
QUAD: rewrite verification/       999.0                       0.022154337029966706
QUAD: rewrite gait_config ranges  0.5866806310579801          0.022154337029966706
QUAD: rewrite gait_config eval    0.022173636756049386        0.022154337029966706
===============================  ==========================  ====================

The last row is the sharpest instance-poisoning case: the submitted gait is the
published baseline and is inside every declared range, so only the rewritten
``eval`` section moved the number.

A fourth defect lived in ``RobotArmCycleTimeOptimization/verification/evaluator.py``
itself: ``_validate_format`` gated everything with ``>`` / ``<``, and every
comparison against NaN is False, so all-NaN ``waypoints`` with
``timestamps=[0.0, 1e-12]`` passed the start/goal tolerance, the joint limits,
the velocity and acceleration limits and the collision query alike -- which
would have scored ``1/(1+1e-12) ~= 1.0``. It did not actually pay out, because
``scipy.interpolate.CubicSpline`` refuses non-finite ``y`` and the resulting
exception was scored -1e18; the gate is fixed anyway, since nothing but a third
party's internal assertion stood between that submission and the ceiling.

Nothing here writes to the repository: attack candidates are given only what the
hardened evaluator leaves them (a scrubbed environment and their own sandbox),
and every attack test re-hashes the scorer-owned files afterwards.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROBOTICS = REPO_ROOT / "benchmarks" / "Robotics"
PID_DIR = ROBOTICS / "PIDTuning"
ARM_DIR = ROBOTICS / "RobotArmCycleTimeOptimization"
QUAD_DIR = ROBOTICS / "QuadrupedGaitOptimization"

TASK_DIRS = (PID_DIR, ARM_DIR, QUAD_DIR)

#: Scores the *pre-hardening* evaluators produced for the shipped baselines.
#: Hardening must not move an honest candidate by a single bit.
PID_BASELINE_COMBINED = 0.036626766599899996
ARM_BASELINE_CYCLE = 2.4224005284777377
ARM_BASELINE_COMBINED = 0.2921925682511491
#: Re-measured in this environment (mujoco 3.12.0). ``baseline/result_log.txt``
#: records 0.02215433702997223 -- a ~2.5e-13 drift from an older mujoco build
#: that predates any hardening, so the *current* value is the fixed point.
QUAD_BASELINE_SPEED = 0.022154337029966706

#: What the attacks scored before the fix, for the record.
PID_PREFIX_SWAP_SCORE = 999.0
ARM_PREFIX_SWAP_SCORE = 1.0
QUAD_PREFIX_SWAP_SCORE = 999.0
QUAD_PREFIX_POISON_SCORE = 0.5866806310579801
QUAD_PREFIX_POISON_INRANGE_SCORE = 0.022173636756049386


@pytest.fixture(scope="module", autouse=True)
def _no_bytecode_cache():
    """Importing an evaluator by path writes ``__pycache__`` next to it.

    ``verification`` and ``frontier_eval`` are readonly paths that the harness
    fingerprints, so a cache this suite drops there is a spurious readonly
    violation for the next run -- and it is exactly what
    ``test_no_stale_bytecode_cache_shadows_the_scorer`` asserts against.
    """
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pid_eval() -> ModuleType:
    return _load("robotics_a_pid_eval", PID_DIR / "frontier_eval" / "evaluator.py")


@pytest.fixture(scope="module")
def arm_eval() -> ModuleType:
    return _load("robotics_a_arm_eval", ARM_DIR / "frontier_eval" / "evaluator.py")


@pytest.fixture(scope="module")
def quad_eval() -> ModuleType:
    return _load("robotics_a_quad_eval", QUAD_DIR / "frontier_eval" / "evaluator.py")


def _metrics(result: Any) -> dict[str, float]:
    return dict(result["metrics"] if isinstance(result, dict) else result.metrics)


def _artifacts(result: Any) -> dict[str, str]:
    return dict(result["artifacts"] if isinstance(result, dict) else result.artifacts)


def _score(module: ModuleType, candidate: Path) -> dict[str, float]:
    return _metrics(module.evaluate(str(candidate), repo_root=REPO_ROOT))


def _candidate(tmp_path: Path, source: str, name: str = "solution.py") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _tree_digest() -> str:
    """Hash every scorer-owned file a candidate might try to rewrite."""
    h = hashlib.sha256()
    for task in TASK_DIRS:
        h.update((task / "verification" / "evaluator.py").read_bytes())
        for ref in sorted((task / "references").iterdir()):
            if ref.is_file():
                h.update(ref.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Source-level contract: the shape of the fix, independent of any run
# ---------------------------------------------------------------------------


def _executable_source(path: Path) -> str:
    """Module source with the module docstring removed.

    The hardened evaluators quote the old buggy code in their docstrings to
    explain what was fixed, so a bare substring search over the whole file would
    match the explanation rather than any live code.
    """
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    doc = ast.get_docstring(tree, clean=False)
    if doc is not None:
        body = tree.body[0]
        assert body.end_lineno is not None
        return "".join(text.splitlines(keepends=True)[body.end_lineno:])
    return text


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=["pid", "arm", "quad"])
def test_candidate_runs_through_the_shared_sandbox(task_dir: Path) -> None:
    source = _executable_source(task_dir / "frontier_eval" / "evaluator.py")
    assert "candidate_sandbox" in source
    assert "run_candidate_isolated" in source
    # Isolation must come from the shared helper, not a bespoke subprocess call.
    assert "subprocess.run(" not in source
    # The child must not simply be handed the path of the tree it must not touch.
    assert "CANDIDATE_ENV_ALLOWLIST" in source
    assert "FRONTIER_ENGINEERING_ROOT" not in source.split("CANDIDATE_ENV_ALLOWLIST", 1)[1].split(")", 1)[0]


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=["pid", "arm", "quad"])
def test_trusted_scorer_is_loaded_before_the_candidate_runs(task_dir: Path) -> None:
    """Invariant 1 of candidate_sandbox: imports happen before the candidate."""
    source = _executable_source(task_dir / "frontier_eval" / "evaluator.py")
    load_scorer = source.index("_load_trusted_scorer(")
    run_candidate = source.index("run_candidate_isolated(")
    assert load_scorer < run_candidate, "the scorer is still fetched after the candidate has run"


@pytest.mark.parametrize("task_dir", [ARM_DIR, QUAD_DIR], ids=["arm", "quad"])
def test_trusted_scorer_is_loaded_from_a_private_copy(task_dir: Path) -> None:
    """Both trusted modules resolve assets relative to their own ``__file__``.

    ARM reaches ``pybullet_data``; QUAD reaches ``references/gait_config.json``
    and ``references/ant.xml``. Loading them from a private staging directory is
    what pins those lookups to bytes captured before the candidate ran.
    """
    source = _executable_source(task_dir / "frontier_eval" / "evaluator.py")
    assert "private_eval = private / \"verification\" / \"evaluator.py\"" in source
    assert "_load_trusted_scorer(private_eval)" in source


def test_arm_pins_the_pybullet_asset_path() -> None:
    """The kuka/plane assets live in writable site-packages, outside the repo."""
    source = _executable_source(ARM_DIR / "frontier_eval" / "evaluator.py")
    stage = source.index("_stage_pybullet_assets(")
    run_candidate = source.index("run_candidate_isolated(")
    assert stage < run_candidate
    assert "trusted.pybullet_data = _PinnedPybulletData(" in source


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=["pid", "arm", "quad"])
def test_readonly_files_covers_the_scorer_owned_material(task_dir: Path) -> None:
    entries = {
        line.strip()
        for line in (task_dir / "frontier_eval" / "readonly_files.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert {"references", "verification", "frontier_eval"} <= entries


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=["pid", "arm", "quad"])
def test_no_stale_bytecode_cache_shadows_the_scorer(task_dir: Path) -> None:
    """A committed .pyc can shadow its .py at import time, so none may be checked in."""
    stale = [
        p.relative_to(task_dir).as_posix()
        for sub in ("verification", "frontier_eval", "references", "scripts", "baseline")
        if (task_dir / sub).is_dir()
        for p in (task_dir / sub).glob("__pycache__/*.pyc")
    ]
    assert stale == []


# ---------------------------------------------------------------------------
# The load-before-run mechanism itself
# ---------------------------------------------------------------------------


def test_a_trusted_module_loaded_first_survives_its_file_being_rewritten(tmp_path: Path) -> None:
    """The property every attack below depends on, isolated from any benchmark.

    ``_load_trusted_scorer`` executes the module *now*; rewriting the file
    afterwards cannot reach the already-bound function object. This is why the
    ordering, not the environment scrub, is the actual fix.
    """
    arm = _load("robotics_a_arm_eval_mech", ARM_DIR / "frontier_eval" / "evaluator.py")
    path = tmp_path / "evaluator.py"
    path.write_text("def evaluate(p):\n    return 42.0\n", encoding="utf-8")
    trusted = arm._load_trusted_scorer(path)
    path.write_text("def evaluate(p):\n    return 999.0\n", encoding="utf-8")
    assert trusted.evaluate(None) == 42.0


# ---------------------------------------------------------------------------
# Honest candidates: the published numbers must not move
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_pid_honest_baseline_scores_the_published_value(pid_eval: ModuleType) -> None:
    metrics = _score(pid_eval, PID_DIR / "scripts" / "init.py")
    assert metrics["valid"] == 1.0
    assert metrics["feasible"] == 1.0
    assert metrics["combined_score"] == PID_BASELINE_COMBINED


@pytest.mark.slow
def test_arm_honest_baseline_scores_the_published_value(arm_eval: ModuleType) -> None:
    metrics = _score(arm_eval, ARM_DIR / "baseline" / "solution.py")
    assert metrics["valid"] == 1.0
    assert metrics["feasible"] == 1.0
    assert metrics["cycle_time_s"] == ARM_BASELINE_CYCLE
    assert metrics["combined_score"] == ARM_BASELINE_COMBINED


@pytest.mark.slow
def test_quad_honest_baseline_scores_the_published_value(quad_eval: ModuleType) -> None:
    metrics = _score(quad_eval, QUAD_DIR / "baseline" / "solution.py")
    assert metrics["valid"] == 1.0
    assert metrics["feasible"] == 1.0
    assert metrics["speed_mps"] == QUAD_BASELINE_SPEED
    assert metrics["combined_score"] == QUAD_BASELINE_SPEED


# ---------------------------------------------------------------------------
# Attack 1: rewrite the scoring function
# ---------------------------------------------------------------------------

_PATCH_SCORER = '''
import json, os
from pathlib import Path

PWN = "def evaluate(*a, **k):\\n    return {score}\\n"

roots = [Path(__file__).resolve().parents[i] for i in range(1, 4)]
roots += [Path.cwd(), Path.cwd().parent]
env_root = os.environ.get("FRONTIER_ENGINEERING_ROOT")
if env_root:
    roots.append(Path(env_root))

for root in roots:
    for rel in ("verification/evaluator.py",
                "benchmarks/Robotics/{task}/verification/evaluator.py"):
        try:
            target = root / rel
            if target.parent.is_dir():
                target.write_text(PWN, encoding="utf-8")
        except Exception:
            pass

json.dump({{"junk": 1}}, open("submission.json", "w"))
'''


@pytest.mark.slow
@pytest.mark.parametrize(
    "fixture_name, task, score, prefix_score",
    [
        ("pid_eval", "PIDTuning", "999.0", PID_PREFIX_SWAP_SCORE),
        ("arm_eval", "RobotArmCycleTimeOptimization", "0.0", ARM_PREFIX_SWAP_SCORE),
        ("quad_eval", "QuadrupedGaitOptimization", "999.0", QUAD_PREFIX_SWAP_SCORE),
    ],
    ids=["pid", "arm", "quad"],
)
def test_rewriting_the_scorer_no_longer_sets_the_score(
    fixture_name: str, task: str, score: str, prefix_score: float, tmp_path: Path, request
) -> None:
    module = request.getfixturevalue(fixture_name)
    before = _tree_digest()
    result = module.evaluate(
        str(_candidate(tmp_path, _PATCH_SCORER.format(task=task, score=score))),
        repo_root=REPO_ROOT,
    )
    metrics, artifacts = _metrics(result), _artifacts(result)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] != prefix_score
    assert "invalid submission" in artifacts["error_message"]
    assert _tree_digest() == before, "attack reached the real benchmark tree"


# ---------------------------------------------------------------------------
# Attack 2: swap the instance the submission is graded against
# ---------------------------------------------------------------------------

_POISON_QUAD_CONFIG = '''
import json, os
from pathlib import Path

roots = [Path(__file__).resolve().parents[i] for i in range(1, 4)]
roots += [Path.cwd(), Path.cwd().parent]
env_root = os.environ.get("FRONTIER_ENGINEERING_ROOT")
if env_root:
    roots.append(Path(env_root))

for root in roots:
    for rel in ("references/gait_config.json",
                "benchmarks/Robotics/QuadrupedGaitOptimization/references/gait_config.json"):
        try:
            path = root / rel
            if not path.is_file():
                continue
            cfg = json.loads(path.read_text(encoding="utf-8-sig"))
            cfg["ranges"] = {{k: [-1e9, 1e9] for k in cfg["ranges"]}}
            cfg["eval"]["control_kp"] = {kp}
            cfg["eval"]["torque_limit"] = 1e9
            cfg["eval"]["pitch_roll_limit_rad"] = 1e9
            cfg["eval"]["min_distance_m"] = -1e9
            path.write_text(json.dumps(cfg), encoding="utf-8")
        except Exception:
            pass

json.dump({params}, open("submission.json", "w"))
'''

_HONEST_GAIT = {
    "step_frequency": 1.8, "duty_factor": 0.42, "step_length": 0.18, "step_height": 0.11,
    "phase_FR": 0.5, "phase_RL": 0.5, "phase_RR": 0.0, "lateral_distance": 0.16,
}
_OUT_OF_RANGE_GAIT = dict(_HONEST_GAIT, step_frequency=3.0, step_length=5.0, step_height=2.0)


@pytest.mark.slow
def test_quad_out_of_range_gait_is_rejected_even_with_a_rewritten_config(
    quad_eval: ModuleType, tmp_path: Path
) -> None:
    """Ranges are enforced from the config captured before the candidate ran."""
    before = _tree_digest()
    source = _POISON_QUAD_CONFIG.format(kp=40.0, params=json.dumps(_OUT_OF_RANGE_GAIT))
    result = quad_eval.evaluate(str(_candidate(tmp_path, source)), repo_root=REPO_ROOT)
    metrics, artifacts = _metrics(result), _artifacts(result)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] != QUAD_PREFIX_POISON_SCORE
    assert "out of range" in artifacts["error_message"]
    assert _tree_digest() == before


@pytest.mark.slow
def test_quad_rewritten_rollout_settings_do_not_move_an_in_range_score(
    quad_eval: ModuleType, tmp_path: Path
) -> None:
    """The sharp case: legal parameters, rewritten ``eval`` section.

    Nothing in the submission is out of bounds, so only the poisoned rollout
    could change the number -- and it must not, because the trusted module was
    imported from a private copy of ``references/`` before the candidate ran.
    """
    before = _tree_digest()
    source = _POISON_QUAD_CONFIG.format(kp=5.0, params=json.dumps(_HONEST_GAIT))
    metrics = _score(quad_eval, _candidate(tmp_path, source))
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] != QUAD_PREFIX_POISON_INRANGE_SCORE
    assert metrics["speed_mps"] == QUAD_BASELINE_SPEED
    assert _tree_digest() == before


# ---------------------------------------------------------------------------
# Attack 3: NaN laundering through the RobotArm limit checks
# ---------------------------------------------------------------------------

_ARM_NAN = '''
import json
nan = float("nan")
json.dump({"waypoints": [[nan] * 7, [nan] * 7], "timestamps": [0.0, 1e-12]},
          open("submission.json", "w"))
'''

_ARM_NAN_MIDDLE = '''
import json
nan = float("nan")
Q_START = [0.0, 0.5, 0.0, -1.5, 0.0, 1.0, 0.0]
Q_GOAL = [1.2, -0.3, 0.8, -0.8, 0.5, 0.8, 1.0]
json.dump({"waypoints": [Q_START, [nan] * 7, Q_GOAL], "timestamps": [0.0, 5e-13, 1e-12]},
          open("submission.json", "w"))
'''


@pytest.mark.slow
@pytest.mark.parametrize("source", [_ARM_NAN, _ARM_NAN_MIDDLE], ids=["all-nan", "nan-in-the-middle"])
def test_arm_non_finite_waypoints_are_rejected(arm_eval: ModuleType, source: str, tmp_path: Path) -> None:
    result = arm_eval.evaluate(str(_candidate(tmp_path, source)), repo_root=REPO_ROOT)
    metrics, artifacts = _metrics(result), _artifacts(result)
    assert metrics["valid"] == 0.0
    # The pre-hardening payout would have been 1/(1+1e-12), i.e. ~1.0.
    assert metrics["combined_score"] < ARM_BASELINE_COMBINED
    assert "must be finite" in artifacts["error_message"]


def test_arm_verification_gate_rejects_non_finite_waypoints() -> None:
    """The underlying gate, not just the scorer-side one.

    ``verification/evaluator.py`` is also the published standalone CLI, so it has
    to reject this on its own; before the fix ``_validate_format`` returned True
    for all-NaN waypoints and only scipy's finite check stopped the exploit.
    """
    numpy = pytest.importorskip("numpy")
    trusted = _load("robotics_a_arm_trusted", ARM_DIR / "verification" / "evaluator.py")
    nan = float("nan")
    timestamps = numpy.array([0.0, 1e-12])
    assert trusted._validate_format(numpy.full((2, 7), nan), timestamps) is False
    assert trusted._validate_format(
        numpy.array([trusted.Q_START, [nan] * 7, trusted.Q_GOAL]),
        numpy.array([0.0, 5e-13, 1e-12]),
    ) is False
    # A well-formed trajectory must still pass, unchanged.
    assert trusted._validate_format(
        numpy.array([trusted.Q_START, trusted.Q_GOAL]), numpy.array([0.0, 2.0])
    ) is True


# ---------------------------------------------------------------------------
# The candidate reports a solution, never a score (invariant 2)
# ---------------------------------------------------------------------------

_SELF_REPORTED = '''
import json
json.dump({
    "score": 1.0e9, "combined_score": 1.0e9, "valid": 1.0, "feasible": True,
    "cycle_time_s": 0.0, "speed_mps": 1.0e9,
    "metrics": {"combined_score": 1.0e9, "valid": 1.0},
    "summary": {"score": 1.0e9},
}, open("submission.json", "w"))
'''


@pytest.mark.slow
@pytest.mark.parametrize("fixture_name", ["pid_eval", "arm_eval", "quad_eval"], ids=["pid", "arm", "quad"])
def test_self_reported_fields_never_reach_the_metrics(
    fixture_name: str, tmp_path: Path, request
) -> None:
    module = request.getfixturevalue(fixture_name)
    metrics = _score(module, _candidate(tmp_path, _SELF_REPORTED))
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] != 1.0e9


@pytest.mark.slow
@pytest.mark.parametrize("fixture_name", ["pid_eval", "arm_eval", "quad_eval"], ids=["pid", "arm", "quad"])
def test_a_crashing_candidate_is_not_scored(fixture_name: str, tmp_path: Path, request) -> None:
    module = request.getfixturevalue(fixture_name)
    source = 'import json, sys\njson.dump({"junk": 1}, open("submission.json", "w"))\nsys.exit(3)\n'
    result = module.evaluate(str(_candidate(tmp_path, source)), repo_root=REPO_ROOT)
    metrics, artifacts = _metrics(result), _artifacts(result)
    assert metrics["valid"] == 0.0
    assert metrics["candidate_returncode"] == 3.0
    assert artifacts["error_message"] == "candidate program exited non-zero"


@pytest.mark.slow
@pytest.mark.parametrize("fixture_name", ["pid_eval", "arm_eval", "quad_eval"], ids=["pid", "arm", "quad"])
def test_a_silent_candidate_is_not_scored(fixture_name: str, tmp_path: Path, request) -> None:
    """A candidate that writes nothing must fail, not inherit a stale submission."""
    module = request.getfixturevalue(fixture_name)
    result = module.evaluate(str(_candidate(tmp_path, "pass\n")), repo_root=REPO_ROOT)
    metrics, artifacts = _metrics(result), _artifacts(result)
    assert metrics["valid"] == 0.0
    assert metrics["candidate_returncode"] == 0.0
    assert "did not generate submission.json" in artifacts["error_message"]
