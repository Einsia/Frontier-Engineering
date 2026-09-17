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
    from benchmarks.OperationsResearch.DynamicCurrentMinimumTimeRouting.baseline.solution import solve as baseline_solve
    from benchmarks.OperationsResearch.DynamicCurrentMinimumTimeRouting.runtime.problem import BASELINE_HOPS, BASELINE_TIME_H, REFERENCE_TIME_H, load_instance, route_metrics
except ModuleNotFoundError:
    from baseline.solution import solve as baseline_solve
    from runtime.problem import BASELINE_HOPS, BASELINE_TIME_H, REFERENCE_TIME_H, load_instance, route_metrics


def evaluate(program_path: str):
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_time_h": 0.0,
        "baseline_time_h": float(BASELINE_TIME_H),
        "reference_time_h": float(REFERENCE_TIME_H),
        "candidate_hops": 0.0,
        "baseline_hops": float(BASELINE_HOPS),
    }
    artifacts = {}
    namespace = runpy.run_path(str(Path(program_path).expanduser().resolve()), run_name="candidate_program")
    solve_fn = namespace.get("solve")
    if not callable(solve_fn):
        artifacts["error_message"] = "candidate must define solve(instance)"
        return metrics, artifacts

    instance = load_instance()
    try:
        baseline_metrics = route_metrics(baseline_solve(instance))
        candidate_metrics = route_metrics(solve_fn(instance))
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts

    candidate_time_h = float(candidate_metrics["time_h"])
    if not math.isfinite(candidate_time_h) or candidate_time_h <= 0:
        artifacts["error_message"] = "candidate time is invalid"
        return metrics, artifacts

    metrics["valid"] = 1.0
    metrics["candidate_time_h"] = candidate_time_h
    metrics["candidate_hops"] = float(candidate_metrics["hops"])
    metrics["baseline_time_h"] = float(baseline_metrics["time_h"])
    metrics["baseline_hops"] = float(baseline_metrics["hops"])
    metrics["combined_score"] = -candidate_time_h
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
