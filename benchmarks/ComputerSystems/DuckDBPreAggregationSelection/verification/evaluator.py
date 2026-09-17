from __future__ import annotations

import argparse
import json
import math
import runpy
import traceback
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    return Path.cwd().resolve()


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_path() -> None:
    import sys

    for p in (_repo_root(), _benchmark_root()):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.ComputerSystems.DuckDBPreAggregationSelection.baseline.solution import select_preaggregations as baseline_select_preaggregations
    from benchmarks.ComputerSystems.DuckDBPreAggregationSelection.runtime.problem import WORKLOAD_MANIFEST, evaluate_selection
except ModuleNotFoundError:
    from baseline.solution import select_preaggregations as baseline_select_preaggregations
    from runtime.problem import WORKLOAD_MANIFEST, evaluate_selection


def evaluate(program_path: str):
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_total_runtime_s": 0.0,
        "baseline_total_runtime_s": 0.0,
        "candidate_setup_runtime_s": 0.0,
        "candidate_workload_runtime_s": 0.0,
    }
    artifacts = {}
    namespace = runpy.run_path(str(Path(program_path).expanduser().resolve()), run_name="candidate_program")
    select_preaggregations = namespace.get("select_preaggregations")
    if not callable(select_preaggregations):
        artifacts["error_message"] = "candidate must define select_preaggregations(workload_manifest)"
        return metrics, artifacts
    try:
        baseline = evaluate_selection(baseline_select_preaggregations(WORKLOAD_MANIFEST))
        candidate = evaluate_selection(select_preaggregations(WORKLOAD_MANIFEST))
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts
    candidate_total = float(candidate["candidate_total_runtime_s"])
    baseline_total = float(candidate["baseline_total_runtime_s"])
    if not math.isfinite(candidate_total) or candidate_total <= 0:
        artifacts["error_message"] = "candidate runtime is invalid"
        return metrics, artifacts
    metrics["valid"] = 1.0
    metrics["candidate_total_runtime_s"] = candidate_total
    metrics["baseline_total_runtime_s"] = baseline_total
    metrics["candidate_setup_runtime_s"] = float(candidate["setup_runtime_s"])
    metrics["candidate_workload_runtime_s"] = float(candidate["candidate_workload_runtime_s"])
    metrics["combined_score"] = -candidate_total
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    parser.add_argument("--metrics-out", default="metrics.json")
    args = parser.parse_args()
    metrics, artifacts = evaluate(args.program)
    Path(args.metrics_out).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if artifacts:
        Path("artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
