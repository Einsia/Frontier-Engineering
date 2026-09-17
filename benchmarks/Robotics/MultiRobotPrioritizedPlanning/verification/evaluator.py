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
    from benchmarks.Robotics.MultiRobotPrioritizedPlanning.baseline.solution import plan_paths as baseline_plan_paths_fn
    from benchmarks.Robotics.MultiRobotPrioritizedPlanning.runtime.problem import GOALS, FREE_GRID, LOWER_BOUND_TOTAL_COST, STARTS, makespan, total_cost, validate_paths
except ModuleNotFoundError:
    from baseline.solution import plan_paths as baseline_plan_paths_fn
    from runtime.problem import GOALS, FREE_GRID, LOWER_BOUND_TOTAL_COST, STARTS, makespan, total_cost, validate_paths


def evaluate(program_path: str) -> tuple[dict[str, float], dict[str, str]]:
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_total_cost": 0.0,
        "baseline_total_cost": 0.0,
        "candidate_makespan": 0.0,
        "lower_bound_total_cost": float(LOWER_BOUND_TOTAL_COST),
    }
    artifacts: dict[str, str] = {}
    namespace = runpy.run_path(str(Path(program_path).expanduser().resolve()), run_name="candidate_program")
    plan_paths_fn = namespace.get("plan_paths")
    if not callable(plan_paths_fn):
        artifacts["error_message"] = "candidate must define plan_paths(grid, starts, goals)"
        return metrics, artifacts
    try:
        baseline_paths = validate_paths(baseline_plan_paths_fn(FREE_GRID, STARTS, GOALS))
        candidate_paths = validate_paths(plan_paths_fn(FREE_GRID, STARTS, GOALS))
        baseline_total_cost = float(total_cost(baseline_paths))
        candidate_total_cost = float(total_cost(candidate_paths))
        candidate_makespan = float(makespan(candidate_paths))
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts
    if not math.isfinite(candidate_total_cost) or candidate_total_cost <= 0:
        artifacts["error_message"] = "candidate total cost is invalid"
        return metrics, artifacts
    metrics["valid"] = 1.0
    metrics["candidate_total_cost"] = candidate_total_cost
    metrics["baseline_total_cost"] = baseline_total_cost
    metrics["candidate_makespan"] = candidate_makespan
    metrics["combined_score"] = -candidate_total_cost
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
