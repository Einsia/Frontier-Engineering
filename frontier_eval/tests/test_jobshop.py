"""Regression tests for the JobShop candidate-isolation hardening.

Two holes are covered here, both of which used to make `combined_score` a
statement by the candidate rather than about it:

* **Instance data came from the candidate.** `evaluate_unified.py` called
  `baseline_mod.load_family_instances()`, so the matrices feasibility was
  checked against *and* the `optimum` used as the scoring denominator were both
  supplied by the thing being scored. A self-consistent one-operation instance
  scored 100.
* **`metadata.optimum` was handed to the candidate.** The full instance dict,
  answer key included, was passed straight into `solve_instance`.

The candidate now runs in a subprocess (`benchmarks/_shared/candidate_sandbox`)
and only ever sees `name` / `duration_matrix` / `machines_matrix`.

These tests need no `job_shop_lib`: the reference solver is a reporting-only
comparison and is skipped by passing `reference_mod=None`.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JOBSHOP_DIR = REPO_ROOT / "benchmarks" / "JobShop"
SHARED_DIR = REPO_ROOT / "benchmarks" / "_shared"
BENCHMARK_JSON = JOBSHOP_DIR / "data" / "benchmark_instances.json"
UNIFIED = JOBSHOP_DIR / "frontier_eval" / "evaluate_unified.py"

FAMILIES = ("abz", "ft", "la", "orb", "swv", "ta", "yn")

# Small, fast family: ft06 is 6x6, ft10 10x10, ft20 20x5.
FAMILY = "ft"
FAMILY_DIR = JOBSHOP_DIR / FAMILY

#: `combined_score` the pre-hardening evaluator produced for the shipped greedy
#: baseline on the full ft family. The whole point of the fix is that an honest
#: candidate's score does not move.
FT_BASELINE_COMBINED_SCORE = 80.34722191602033

if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def eval_mod() -> ModuleType:
    return _load("jobshop_test_eval_ft", FAMILY_DIR / "verification" / "evaluate.py")


@pytest.fixture(scope="module")
def instances(eval_mod: ModuleType) -> list[dict]:
    return eval_mod.load_family_instances(BENCHMARK_JSON)


def _write_candidate(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "candidate.py"
    path.write_text(source, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Problem A: the evaluator owns the instance data
# --------------------------------------------------------------------------


def test_candidate_modules_no_longer_load_instance_data() -> None:
    """The candidate contract is `solve_instance` and nothing else."""
    banned = (
        "load_family_instances",
        "load_benchmark_json",
        "load_instance_by_name",
        "_benchmark_json_path",
        "JOBSHOP_BENCHMARK_JSON",
        "benchmark_instances.json",
    )
    for family in FAMILIES:
        source = (JOBSHOP_DIR / family / "baseline" / "init.py").read_text(encoding="utf-8")
        assert "def solve_instance(" in source, family
        for name in banned:
            assert name not in source, f"{family}/baseline/init.py still references {name}"


def test_unified_reads_trusted_data_and_never_imports_the_candidate() -> None:
    source = UNIFIED.read_text(encoding="utf-8")
    assert "baseline_mod" not in source
    assert 'os.environ.setdefault("JOBSHOP_BENCHMARK_JSON"' not in source
    assert "TRUSTED_BENCHMARK_JSON" in source


def test_forged_instance_data_is_ignored(tmp_path: Path) -> None:
    """The archived exploit: a candidate that supplies its own tiny instance.

    Before the fix, `load_family_instances()` came from this module, so both the
    feasibility check and the scoring denominator used the fake instance and the
    run scored 100. Now the fake instance is never read, the schedule is checked
    against the real ft matrices, and the run is invalid.
    """
    benchmark_dir = tmp_path / "benchmark"
    shutil.copytree(FAMILY_DIR, benchmark_dir)
    (benchmark_dir / "baseline" / "init.py").write_text(
        '''# EVOLVE-BLOCK-START
"""Malicious: claims a one-operation instance whose optimum it always hits."""
from __future__ import annotations

FAKE = {
    "name": "ft06",
    "duration_matrix": [[1]],
    "machines_matrix": [[0]],
    "metadata": {"optimum": 1, "lower_bound": 1, "upper_bound": 1},
}


def load_family_instances():
    return [dict(FAKE)]


def load_instance_by_name(name):
    return dict(FAKE)


def solve_instance(instance):
    return {
        "makespan": 1,
        "machine_schedules": [
            [{"job_id": 0, "operation_index": 0, "start_time": 0, "end_time": 1}]
        ],
    }
# EVOLVE-BLOCK-END
''',
        encoding="utf-8",
    )

    metrics, artifacts = _run_unified(benchmark_dir, tmp_path, instances=["ft06", "ft10"])

    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == 0.0
    assert metrics["baseline_failures"] == 2.0
    # Scored against the real instances, not the forged one.
    assert artifacts["selected_instances"] == ["ft06", "ft10"]
    assert artifacts["instances_source"] == str(BENCHMARK_JSON)
    errors = artifacts["baseline_errors"]
    assert len(errors) == 2
    assert "machine_schedules has 1 machines, expected 6" in errors[0]["error"]


def _run_unified(benchmark_dir: Path, out_dir: Path, instances: list[str] | None = None) -> tuple[dict, dict]:
    metrics_out = out_dir / "metrics.json"
    artifacts_out = out_dir / "artifacts.json"
    cmd = [
        sys.executable,
        str(UNIFIED),
        "--benchmark-dir",
        str(benchmark_dir),
        "--metrics-out",
        str(metrics_out),
        "--artifacts-out",
        str(artifacts_out),
        "--stdout-log",
        str(out_dir / "eval.stdout.txt"),
        "--stderr-log",
        str(out_dir / "eval.stderr.txt"),
        "--reference-time-limit",
        "0.1",
    ]
    if instances:
        cmd += ["--instances", *instances]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr
    return (
        json.loads(metrics_out.read_text(encoding="utf-8")),
        json.loads(artifacts_out.read_text(encoding="utf-8")),
    )


# --------------------------------------------------------------------------
# Problem B: the candidate never sees the optimum
# --------------------------------------------------------------------------


def test_public_view_strips_all_metadata(eval_mod: ModuleType, instances: list[dict]) -> None:
    instance = instances[0]
    assert instance["metadata"]["optimum"] == 55  # trusted side still has it

    view = eval_mod.public_instance_view(instance)
    assert set(view) == set(eval_mod.PUBLIC_INSTANCE_FIELDS) == {
        "name",
        "duration_matrix",
        "machines_matrix",
    }
    assert "metadata" not in view
    assert json.dumps(view).find("optimum") == -1


def test_candidate_subprocess_receives_no_optimum(
    eval_mod: ModuleType, instances: list[dict], tmp_path: Path
) -> None:
    """Observe what actually crosses the process boundary, not just the projection."""
    probe = tmp_path / "seen.json"
    candidate = _write_candidate(
        tmp_path,
        f'''
import json, pathlib


def solve_instance(instance):
    pathlib.Path({str(probe)!r}).write_text(json.dumps(sorted(instance)), encoding="utf-8")
    durations = instance["duration_matrix"]
    machines = instance["machines_matrix"]
    num_machines = max(max(row) for row in machines) + 1
    schedules = [[] for _ in range(num_machines)]
    job_ready = [0] * len(durations)
    machine_ready = [0] * num_machines
    for job_id, row in enumerate(durations):
        for op_idx, duration in enumerate(row):
            machine_id = machines[job_id][op_idx]
            start = max(job_ready[job_id], machine_ready[machine_id])
            end = start + duration
            schedules[machine_id].append(
                {{"job_id": job_id, "operation_index": op_idx,
                  "start_time": start, "end_time": end}}
            )
            job_ready[job_id] = end
            machine_ready[machine_id] = end
    return {{"machine_schedules": schedules}}
''',
    )

    results = eval_mod.evaluate_instances(instances[:1], 0.0, candidate, None)

    assert json.loads(probe.read_text(encoding="utf-8")) == [
        "duration_matrix",
        "machines_matrix",
        "name",
    ]
    # A schedule with no self-reported makespan is the new contract, and valid.
    assert results[0].baseline_valid, results[0].baseline_note
    assert results[0].baseline_makespan is not None


def test_candidate_env_does_not_point_back_at_the_benchmark_data(
    eval_mod: ModuleType, instances: list[dict], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stripping `metadata` is pointless if the candidate can just open the JSON.

    The subprocess gets a narrow allowlist, so FRONTIER_ENGINEERING_ROOT (and
    the retired JOBSHOP_BENCHMARK_JSON) never reach it.
    """
    monkeypatch.setenv("FRONTIER_ENGINEERING_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("JOBSHOP_BENCHMARK_JSON", str(BENCHMARK_JSON))

    probe = tmp_path / "env.json"
    candidate = _write_candidate(
        tmp_path,
        f"""
import json, os, pathlib


def solve_instance(instance):
    pathlib.Path({str(probe)!r}).write_text(json.dumps(sorted(os.environ)), encoding="utf-8")
    return {{"machine_schedules": []}}
""",
    )

    eval_mod.evaluate_instances(instances[:1], 0.0, candidate, None)

    seen = json.loads(probe.read_text(encoding="utf-8"))
    assert "FRONTIER_ENGINEERING_ROOT" not in seen
    assert "JOBSHOP_BENCHMARK_JSON" not in seen
    assert set(seen) <= set(eval_mod.CANDIDATE_ENV_ALLOWLIST)


def test_candidate_reaching_for_metadata_fails(
    eval_mod: ModuleType, instances: list[dict], tmp_path: Path
) -> None:
    """The archived early-stopping trick (`stop when makespan == optimum`)."""
    candidate = _write_candidate(
        tmp_path,
        "def solve_instance(instance):\n"
        "    target = instance['metadata']['optimum']\n"
        "    return {'makespan': target, 'machine_schedules': []}\n",
    )

    results = eval_mod.evaluate_instances(instances[:1], 0.0, candidate, None)

    assert not results[0].baseline_valid
    note = results[0].baseline_note or ""
    assert "not produced" in note or "non-zero" in note
    assert results[0].baseline_makespan is None
    # The scorer still knows the optimum; only the candidate does not.
    assert results[0].optimum == 55


# --------------------------------------------------------------------------
# The honest path must be untouched
# --------------------------------------------------------------------------


def test_honest_candidate_scores_are_unchanged(eval_mod: ModuleType, instances: list[dict]) -> None:
    candidate = FAMILY_DIR / "baseline" / "init.py"
    results = eval_mod.evaluate_instances(instances, 0.0, candidate, None)

    assert [row.name for row in results] == ["ft06", "ft10", "ft20"]
    assert all(row.baseline_valid for row in results), [r.baseline_note for r in results]

    # Same schedule the greedy produces here, scored the same way.
    baseline_mod = _load("jobshop_test_baseline_ft", candidate)
    scores = []
    for row, instance in zip(results, instances):
        expected = baseline_mod.solve_instance(eval_mod.public_instance_view(instance))
        assert row.baseline_makespan == expected["makespan"]
        target = row.optimum if row.optimum is not None else row.upper_bound
        scores.append(min(100.0, 100.0 * target / row.baseline_makespan))

    combined = sum(scores) / len(scores)
    assert combined == pytest.approx(FT_BASELINE_COMBINED_SCORE)


def test_self_reported_makespan_cannot_beat_the_recomputed_one(
    eval_mod: ModuleType, instances: list[dict], tmp_path: Path
) -> None:
    """A feasible schedule plus a flattering makespan is a rejection, not a 100."""
    honest = (FAMILY_DIR / "baseline" / "init.py").read_text(encoding="utf-8")
    candidate = _write_candidate(
        tmp_path,
        honest.replace(
            '    return {\n        "makespan": makespan,',
            '    return {\n        "makespan": 1,',
        ),
    )

    results = eval_mod.evaluate_instances(instances[:1], 0.0, candidate, None)

    assert not results[0].baseline_valid
    assert "does not match recomputed" in (results[0].baseline_note or "")
