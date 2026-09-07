"""Candidate-isolation regressions for two Robotics path-planning benchmarks.

Covered here:

* ``Robotics/UAVInspectionCoverageWithWind``
* ``Robotics/DynamicObstacleAvoidanceNavigation``

Both shipped the same ``frontier_eval/evaluator.py``: copy the benchmark tree to
a scratch dir, run the candidate *inside* it, then ``exec_module`` the scorer
back out of that same tree and let it locate ``references/scenarios.json``
relative to its own ``__file__``. Two independent holes fell out of that:

1. **The scorer was loaded from a directory the candidate had just written to.**
   A candidate that overwrote ``../verification/evaluator.py`` was graded by its
   own code. Measured: UAV ``combined_score`` 28.85 -> 1.0e9; navigation
   0.0722 -> 1.0 (the ceiling of ``1/(1+t)``).
2. **The environment being graded came from the same writable copy** -- the
   "candidate supplies the instance" defect already found in JobShop. A
   candidate that deleted the obstacles and moved the goals/inspection points
   onto the start scored 100.0 (UAV) and 1.0 (navigation) with an all-zero
   control sequence.

The candidate now runs through ``benchmarks/_shared/candidate_sandbox`` in a
minimal staged tree holding only itself and its own copy of the scenes. The
trusted scenes and the trusted scoring module are read before it starts, from
the pristine benchmark directory, and every physical quantity -- coverage,
energy, collisions, bounds, arrival time, feasibility -- is recomputed by the
scorer from the returned trajectory.

Nothing here writes to the repository; every candidate lives in ``tmp_path``.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROBOTICS = REPO_ROOT / "benchmarks" / "Robotics"
UAV_DIR = ROBOTICS / "UAVInspectionCoverageWithWind"
NAV_DIR = ROBOTICS / "DynamicObstacleAvoidanceNavigation"

#: Scores the *pre-hardening* evaluator produced for the shipped baselines.
#: Hardening must not move an honest candidate by a single bit.
UAV_BASELINE_COMBINED = 28.851886471062496
NAV_BASELINE_COMBINED = 0.07220216606498171
NAV_BASELINE_ARRIVAL = 12.850000000000046

#: What the two attacks scored before the fix, for the record.
UAV_PREFIX_PATCH_SCORE = 1.0e9
UAV_PREFIX_SWAP_SCORE = 100.0
NAV_PREFIX_ATTACK_SCORE = 1.0


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module", autouse=True)
def _no_bytecode_cache():
    """Importing an evaluator by path writes ``__pycache__`` next to it.

    ``verification`` and ``frontier_eval`` are readonly paths that the harness
    fingerprints, so a cache this suite drops there is a spurious readonly
    violation for the next run -- and, without this, the second consecutive run
    of this file fails its own
    ``test_no_stale_bytecode_cache_shadows_the_scorer``.
    """
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous


@pytest.fixture(scope="module")
def uav_eval() -> ModuleType:
    return _load("robotics_b_uav_eval", UAV_DIR / "frontier_eval" / "evaluator.py")


@pytest.fixture(scope="module")
def nav_eval() -> ModuleType:
    return _load("robotics_b_nav_eval", NAV_DIR / "frontier_eval" / "evaluator.py")


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
    h = hashlib.sha256()
    for task in (UAV_DIR, NAV_DIR):
        for rel in ("verification/evaluator.py", "references/scenarios.json"):
            h.update((task / rel).read_bytes())
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
        lines = text.splitlines(keepends=True)
        assert body.end_lineno is not None
        return "".join(lines[body.end_lineno:])
    return text


@pytest.mark.parametrize("task_dir", [UAV_DIR, NAV_DIR], ids=["uav", "nav"])
def test_evaluator_never_loads_the_scorer_from_the_candidate_sandbox(task_dir: Path) -> None:
    path = task_dir / "frontier_eval" / "evaluator.py"
    source = _executable_source(path)

    # The defining bug: the module handed to exec_module came from `sandbox_task`,
    # a directory the candidate had already run in. It must not survive in code
    # (the docstring may still describe it -- see _executable_source).
    assert "sandbox_task" not in source
    assert "copytree" not in source, "the whole benchmark tree is no longer copied for the candidate"

    # The scorer is loaded from the pristine benchmark dir, and it is loaded via
    # a helper that is called before the candidate is ever started.
    assert "_load_trusted_scorer" in source
    assert "trusted_eval_src = benchmark_dir" in source

    # Isolation comes from the shared helper, not from a bespoke subprocess call.
    assert "candidate_sandbox" in source
    assert "run_candidate_isolated" in source
    assert "subprocess.run(" not in source


@pytest.mark.parametrize("task_dir", [UAV_DIR, NAV_DIR], ids=["uav", "nav"])
def test_trusted_inputs_are_read_before_the_candidate_runs(task_dir: Path) -> None:
    """Invariant 1 of candidate_sandbox: imports happen before the candidate."""
    source = _executable_source(task_dir / "frontier_eval" / "evaluator.py")
    read_scenarios = source.index("scenarios_bytes = scenarios_src.read_bytes()")
    load_scorer = source.index("trusted = _load_trusted_scorer(trusted_eval_src)")
    run_candidate = source.index("run_candidate_isolated(")
    assert read_scenarios < run_candidate
    assert load_scorer < run_candidate


@pytest.mark.parametrize("task_dir", [UAV_DIR, NAV_DIR], ids=["uav", "nav"])
def test_readonly_files_covers_the_scorer_owned_material(task_dir: Path) -> None:
    entries = {
        line.strip()
        for line in (task_dir / "frontier_eval" / "readonly_files.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    # The scenes, the scorer and the harness glue must all be fingerprinted, and
    # so must the published baseline numbers -- otherwise an agent can edit
    # result_log.txt and restate what "the baseline scored".
    assert {"references", "verification", "frontier_eval"} <= entries
    assert "baseline/result_log.txt" in entries


@pytest.mark.parametrize("task_dir", [UAV_DIR, NAV_DIR], ids=["uav", "nav"])
def test_no_stale_bytecode_cache_shadows_the_scorer(task_dir: Path) -> None:
    """A committed .pyc can shadow its .py at import time, so none may be checked in.

    The harness fingerprints bytecode caches deliberately (see
    ``_should_ignore_fingerprint_entry``), and both ``verification`` and
    ``frontier_eval`` are readonly paths, so a cache checked in here is both a
    shadowing vector and a guaranteed spurious readonly violation.
    """
    stale = [
        p.relative_to(task_dir).as_posix()
        for sub in ("verification", "frontier_eval", "references")
        for p in (task_dir / sub).glob("__pycache__/*.pyc")
    ]
    assert stale == []


# ---------------------------------------------------------------------------
# Honest candidates: the published numbers must not move
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_uav_honest_baseline_scores_the_published_value(uav_eval: ModuleType) -> None:
    metrics = _score(uav_eval, UAV_DIR / "baseline" / "solution.py")
    assert metrics["valid"] == 1.0
    assert metrics["feasible"] == 1.0
    assert metrics["combined_score"] == UAV_BASELINE_COMBINED
    assert metrics["coverage_objective"] == UAV_BASELINE_COMBINED


@pytest.mark.slow
def test_nav_honest_baseline_scores_the_published_value(nav_eval: ModuleType) -> None:
    metrics = _score(nav_eval, NAV_DIR / "baseline" / "solution.py")
    assert metrics["valid"] == 1.0
    assert metrics["feasible"] == 1.0
    assert metrics["arrival_time_s"] == NAV_BASELINE_ARRIVAL
    assert metrics["combined_score"] == NAV_BASELINE_COMBINED


@pytest.mark.slow
@pytest.mark.parametrize(
    "task_dir, fixture_name, expected",
    [
        (UAV_DIR, "uav_eval", UAV_BASELINE_COMBINED),
        (NAV_DIR, "nav_eval", NAV_BASELINE_COMBINED),
    ],
    ids=["uav", "nav"],
)
def test_submission_written_next_to_file_still_scores(
    task_dir: Path, fixture_name: str, expected: float, tmp_path: Path, request
) -> None:
    """The staged tree puts cwd and ``__file__``'s directory in different places.

    All 28 archived candidates write ``open("submission.json", "w")`` relative to
    cwd, but the pre-hardening evaluator ran them with cwd == ``__file__``'s
    directory, so both spellings used to work. The fallback branch keeps that
    true; without it this candidate would score as "did not generate
    submission.json".
    """
    module = request.getfixturevalue(fixture_name)
    source = (task_dir / "baseline" / "solution.py").read_text(encoding="utf-8")
    old = 'with open("submission.json", "w", encoding="utf-8") as f:'
    assert source.count(old) == 1
    new = 'with open(Path(__file__).resolve().parent / "submission.json", "w", encoding="utf-8") as f:'
    metrics = _score(module, _candidate(tmp_path, source.replace(old, new)))
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == expected


# ---------------------------------------------------------------------------
# Attack 1: rewrite the scoring function
# ---------------------------------------------------------------------------

_PATCH_SCORER = '''
import json
from pathlib import Path

PWN = ("def evaluate(submission_path, scenarios_path=None):\\n"
       "    return {{'score': {score}, 'feasible': True, 'details': {{'pwned': True}}}}\\n")

for root in (Path(__file__).resolve().parents[1], Path.cwd(), Path.cwd().parent):
    for rel in ("verification/evaluator.py", "frontier_eval/evaluator.py"):
        try:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(PWN, encoding="utf-8")
        except Exception:
            pass
    for sub in ("verification", "frontier_eval"):
        try:
            for pyc in (root / sub / "__pycache__").glob("*.pyc"):
                pyc.unlink()
        except Exception:
            pass

json.dump({{"scenarios": []}}, open("submission.json", "w"))
'''


@pytest.mark.slow
@pytest.mark.parametrize(
    "fixture_name, score", [("uav_eval", "1.0e9"), ("nav_eval", "0.0")], ids=["uav", "nav"]
)
def test_rewriting_the_scorer_no_longer_sets_the_score(
    fixture_name: str, score: str, tmp_path: Path, request
) -> None:
    module = request.getfixturevalue(fixture_name)
    before = _tree_digest()
    metrics = _score(module, _candidate(tmp_path, _PATCH_SCORER.format(score=score)))
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] != UAV_PREFIX_PATCH_SCORE
    assert metrics["combined_score"] != NAV_PREFIX_ATTACK_SCORE
    assert _tree_digest() == before, "attack reached the real benchmark tree"


# ---------------------------------------------------------------------------
# Attack 2: swap the environment the submission is graded against
# ---------------------------------------------------------------------------

_SWAP_SCENARIOS = '''
import json
from pathlib import Path

cfg_path = Path(__file__).resolve().parents[1] / "references" / "scenarios.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))

entries = []
for scene in cfg["scenarios"]:
    scene["static_obstacles"] = []
    scene["dynamic_obstacles"] = []
    scene["no_fly_zones"] = []
    if "goal" in scene:
        scene["goal"] = list(scene["start"][:2])
        dim = 2
    else:
        scene["inspection_points"] = [list(scene["start"][:3])]
        scene["wind"] = {"base": [0, 0, 0], "amplitude": [0, 0, 0],
                         "frequency": [0, 0, 0], "phase": [0, 0, 0]}
        dim = 3
    scene["T_max"] = 0.5
    entries.append({
        "id": scene["id"],
        "timestamps": [0.0, 0.5],
        "controls": [[0.0] * dim, [0.0] * dim],
        # self-reported everything, none of which the scorer may believe
        "time": 0.0, "collisions": 0, "coverage_ratio": 1.0,
        "success": True, "scene_score": 1.0e9,
    })

try:
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
except Exception:
    pass

json.dump({
    "scenarios": entries,
    "score": 1.0e9, "feasible": True,
    "summary": {"score": 1.0e9, "combined_score": 1.0e9},
    "metrics": {"combined_score": 1.0e9, "valid": 1.0},
}, open("submission.json", "w"))
'''


@pytest.mark.slow
def test_uav_swapped_scenarios_are_ignored(uav_eval: ModuleType, tmp_path: Path) -> None:
    """Scored against the real scenes, a do-nothing trajectory covers nothing."""
    before = _tree_digest()
    metrics = _score(uav_eval, _candidate(tmp_path, _SWAP_SCENARIOS))
    assert metrics["combined_score"] != UAV_PREFIX_SWAP_SCORE
    # Drifting on the wind with zero control is physically feasible but useless.
    assert metrics["combined_score"] == pytest.approx(0.0, abs=1e-6)
    assert metrics["combined_score"] < UAV_BASELINE_COMBINED
    assert _tree_digest() == before


@pytest.mark.slow
def test_nav_swapped_scenarios_are_ignored(nav_eval: ModuleType, tmp_path: Path) -> None:
    """Against the real scenes the robot never leaves the start, so: infeasible."""
    before = _tree_digest()
    result = nav_eval.evaluate(str(_candidate(tmp_path, _SWAP_SCENARIOS)), repo_root=REPO_ROOT)
    metrics, artifacts = _metrics(result), _artifacts(result)
    assert metrics["valid"] == 0.0
    assert metrics["feasible"] == 0.0
    assert metrics["combined_score"] != NAV_PREFIX_ATTACK_SCORE
    assert "infeasible" in artifacts["error_message"]
    assert _tree_digest() == before


# ---------------------------------------------------------------------------
# The candidate reports a solution, never a score (invariant 2)
# ---------------------------------------------------------------------------

_SELF_REPORTED = '''
import json
from pathlib import Path

cfg = json.loads((Path(__file__).resolve().parents[1] / "references" / "scenarios.json")
                 .read_text(encoding="utf-8-sig"))
dim = 2 if "goal" in cfg["scenarios"][0] else 3
json.dump({
    "scenarios": [
        {"id": s["id"], "timestamps": [0.0, 0.1], "controls": [[0.0] * dim] * 2,
         "success": True, "time": 0.0, "collisions": 0, "coverage_ratio": 1.0,
         "scene_score": 1.0e9, "score": 1.0e9}
        for s in cfg["scenarios"]
    ],
    "score": 1.0e9, "combined_score": 1.0e9, "feasible": True, "valid": 1.0,
    "summary": {"score": 1.0e9, "combined_score": 1.0e9},
    "metrics": {"combined_score": 1.0e9, "valid": 1.0, "feasible": 1.0},
}, open("submission.json", "w"))
'''


@pytest.mark.slow
@pytest.mark.parametrize("fixture_name", ["uav_eval", "nav_eval"], ids=["uav", "nav"])
def test_self_reported_fields_never_reach_the_metrics(fixture_name: str, tmp_path: Path, request) -> None:
    module = request.getfixturevalue(fixture_name)
    metrics = _score(module, _candidate(tmp_path, _SELF_REPORTED))
    assert metrics["combined_score"] != 1.0e9
    assert metrics["combined_score"] <= max(UAV_BASELINE_COMBINED, NAV_BASELINE_COMBINED)


# ---------------------------------------------------------------------------
# Scorer-side structural validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_name, dim", [("uav_eval", 3), ("nav_eval", 2)], ids=["uav", "nav"])
def test_control_dimension_matches_the_task(fixture_name: str, dim: int, request) -> None:
    assert request.getfixturevalue(fixture_name).CONTROL_DIM == dim


@pytest.mark.parametrize("fixture_name, dim", [("uav_eval", 3), ("nav_eval", 2)], ids=["uav", "nav"])
@pytest.mark.parametrize(
    "mutate, expect",
    [
        (lambda e, d: e.update(controls=[[float("nan")] * d, [0.0] * d]), "finite"),
        (lambda e, d: e.update(controls=[[float("inf")] * d, [0.0] * d]), "finite"),
        (lambda e, d: e.update(timestamps=[0.0, float("nan")]), "finite"),
        (lambda e, d: e.update(controls=[[0.0] * (d + 1), [0.0] * (d + 1)]), "list of"),
        (lambda e, d: e.update(id="scene_does_not_exist"), "not a known scene"),
        (lambda e, d: e.update(timestamps=[0.0]), "len(timestamps) != len(controls)"),
    ],
    ids=["nan-control", "inf-control", "nan-timestamp", "wrong-dim", "unknown-id", "length-mismatch"],
)
def test_malformed_trajectories_are_rejected(
    fixture_name: str, dim: int, mutate, expect: str, request
) -> None:
    """NaN slips past the simulator: every ``NaN > limit`` comparison is False."""
    module = request.getfixturevalue(fixture_name)
    entry: dict[str, Any] = {"id": "scene_1", "timestamps": [0.0, 0.1], "controls": [[0.0] * dim] * 2}
    mutate(entry, dim)
    clean, reason = module._validate_submission({"scenarios": [entry]}, ["scene_1", "scene_2"])
    assert clean is None
    assert expect in reason


@pytest.mark.parametrize("fixture_name, dim", [("uav_eval", 3), ("nav_eval", 2)], ids=["uav", "nav"])
def test_duplicate_scene_entries_are_rejected(fixture_name: str, dim: int, request) -> None:
    module = request.getfixturevalue(fixture_name)
    entry = {"id": "scene_1", "timestamps": [0.0, 0.1], "controls": [[0.0] * dim] * 2}
    clean, reason = module._validate_submission({"scenarios": [entry, dict(entry)]}, ["scene_1"])
    assert clean is None
    assert "duplicate" in reason


@pytest.mark.parametrize("fixture_name, dim", [("uav_eval", 3), ("nav_eval", 2)], ids=["uav", "nav"])
def test_validation_strips_everything_but_the_trajectory(fixture_name: str, dim: int, request) -> None:
    module = request.getfixturevalue(fixture_name)
    entry = {
        "id": "scene_1", "timestamps": [0.0, 0.1], "controls": [[0.0] * dim] * 2,
        "score": 1.0e9, "success": True, "collisions": 0,
    }
    clean, reason = module._validate_submission({"scenarios": [entry]}, ["scene_1"])
    assert reason == "ok"
    assert set(clean["scenarios"][0]) == {"id", "timestamps", "controls"}


@pytest.mark.parametrize("fixture_name", ["uav_eval", "nav_eval"], ids=["uav", "nav"])
def test_sample_count_is_capped(fixture_name: str, request) -> None:
    module = request.getfixturevalue(fixture_name)
    n = module.MAX_SAMPLES_PER_SCENARIO + 1
    entry = {"id": "scene_1", "timestamps": [0.0] * n, "controls": [[0.0] * module.CONTROL_DIM] * n}
    clean, reason = module._validate_submission({"scenarios": [entry]}, ["scene_1"])
    assert clean is None
    assert "exceeds" in reason


# ---------------------------------------------------------------------------
# Invariant 3: a crash is a failure, even with a submission on disk
# ---------------------------------------------------------------------------

_CRASH_AFTER_WRITING = '''
import json, sys
from pathlib import Path

cfg = json.loads((Path(__file__).resolve().parents[1] / "references" / "scenarios.json")
                 .read_text(encoding="utf-8-sig"))
dim = 2 if "goal" in cfg["scenarios"][0] else 3
json.dump({"scenarios": [{"id": s["id"], "timestamps": [0.0, 0.1],
                          "controls": [[0.0] * dim] * 2} for s in cfg["scenarios"]]},
          open("submission.json", "w"))
sys.exit(3)
'''


@pytest.mark.slow
@pytest.mark.parametrize("fixture_name", ["uav_eval", "nav_eval"], ids=["uav", "nav"])
def test_nonzero_exit_is_a_failure_even_with_a_submission(
    fixture_name: str, tmp_path: Path, request
) -> None:
    module = request.getfixturevalue(fixture_name)
    result = module.evaluate(str(_candidate(tmp_path, _CRASH_AFTER_WRITING)), repo_root=REPO_ROOT)
    metrics, artifacts = _metrics(result), _artifacts(result)
    assert metrics["valid"] == 0.0
    assert metrics["candidate_returncode"] == 3.0
    assert "non-zero" in artifacts["error_message"]


# ---------------------------------------------------------------------------
# What the candidate can see
# ---------------------------------------------------------------------------

_REPORT_ENVIRONMENT = '''
import json, os, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
json.dump({
    "scenarios": [],
    "_probe": {
        "tree": sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()),
        "env": sorted(os.environ),
    },
}, open("submission.json", "w"))
print(json.dumps({"tree": sorted(p.relative_to(root).as_posix()
                                 for p in root.rglob("*") if p.is_file()),
                  "env": sorted(os.environ)}))
'''


@pytest.mark.slow
@pytest.mark.parametrize("fixture_name", ["uav_eval", "nav_eval"], ids=["uav", "nav"])
def test_candidate_sandbox_holds_no_scorer_material(fixture_name: str, tmp_path: Path, request) -> None:
    module = request.getfixturevalue(fixture_name)
    result = module.evaluate(str(_candidate(tmp_path, _REPORT_ENVIRONMENT)), repo_root=REPO_ROOT)
    probe = json.loads(_artifacts(result)["candidate_stdout"].strip().splitlines()[-1])

    # Exactly the candidate and the scenes it is entitled to read.
    assert set(probe["tree"]) == {"baseline/solution.py", "references/scenarios.json"}

    # No verification code, no reference solution, no result log.
    assert not any("verification" in p or "result_log" in p for p in probe["tree"])

    # And it is not simply handed the location of the real repository.
    assert "FRONTIER_ENGINEERING_ROOT" not in probe["env"]
    assert "FRONTIER_EVAL_UNIFIED_BENCHMARK_DIR" not in probe["env"]


@pytest.mark.slow
@pytest.mark.parametrize("fixture_name", ["uav_eval", "nav_eval"], ids=["uav", "nav"])
def test_trusted_artifact_hashes_are_reported(fixture_name: str, request) -> None:
    """The digests the harness's source-tree fingerprint check can be read against."""
    module = request.getfixturevalue(fixture_name)
    task_dir = UAV_DIR if fixture_name == "uav_eval" else NAV_DIR
    artifacts = _artifacts(module.evaluate(str(task_dir / "baseline" / "solution.py"), repo_root=REPO_ROOT))
    expected_scen = hashlib.sha256((task_dir / "references" / "scenarios.json").read_bytes()).hexdigest()
    expected_eval = hashlib.sha256((task_dir / "verification" / "evaluator.py").read_bytes()).hexdigest()
    assert artifacts["trusted_scenarios_sha256"] == expected_scen
    assert artifacts["trusted_evaluator_sha256"] == expected_eval


# ---------------------------------------------------------------------------
# End-to-end through run_eval.py, the way the harness invokes it
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize(
    "task_dir, expected", [(UAV_DIR, UAV_BASELINE_COMBINED), (NAV_DIR, NAV_BASELINE_COMBINED)],
    ids=["uav", "nav"],
)
def test_run_eval_end_to_end(task_dir: Path, expected: float, tmp_path: Path) -> None:
    metrics_out = tmp_path / "metrics.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(task_dir / "frontier_eval" / "run_eval.py"),
            "--candidate", str(task_dir / "baseline" / "solution.py"),
            "--metrics-out", str(metrics_out),
            "--artifacts-out", str(tmp_path / "artifacts.json"),
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=600,
        env={**dict(__import__("os").environ),
             "FRONTIER_ENGINEERING_ROOT": str(REPO_ROOT),
             "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    metrics = json.loads(metrics_out.read_text(encoding="utf-8"))
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == expected
