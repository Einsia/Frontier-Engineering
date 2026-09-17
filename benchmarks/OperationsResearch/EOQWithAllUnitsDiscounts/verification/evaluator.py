from __future__ import annotations

import argparse
import json
import math
import runpy
import traceback
from pathlib import Path


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    return Path.cwd().resolve()


def _ensure_import_path() -> None:
    import sys

    repo_root = _repo_root()
    benchmark_root = _benchmark_root()
    for p in (repo_root, benchmark_root):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.OperationsResearch.EOQWithAllUnitsDiscounts.runtime.problem import CASES, evaluate_solution
    from benchmarks.OperationsResearch.EOQWithAllUnitsDiscounts.baseline.solution import solve as baseline_solve
except ModuleNotFoundError:
    from runtime.problem import CASES, evaluate_solution
    from baseline.solution import solve as baseline_solve


def evaluate(program_path: str) -> tuple[dict[str, float], dict[str, str]]:
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "avg_cost": 0.0,
        "avg_cost_ratio": 0.0,
        "num_cases": 0.0,
    }
    artifacts: dict[str, str] = {}

    program = Path(program_path).expanduser().resolve()
    namespace = runpy.run_path(str(program), run_name="candidate_program")
    solve = namespace.get("solve")
    if not callable(solve):
        artifacts["error_message"] = "candidate file must define solve(instance)"
        return metrics, artifacts

    total_cost = 0.0
    total_ratio = 0.0
    for idx, case in enumerate(CASES):
        baseline_solution = baseline_solve(case)
        baseline_eval = evaluate_solution(case, baseline_solution)
        if not baseline_eval["valid"]:
            artifacts["error_message"] = f"internal baseline invalid on case {idx}"
            return metrics, artifacts

        try:
            candidate_solution = solve(case)
            candidate_eval = evaluate_solution(case, candidate_solution)
        except Exception:
            artifacts["error_message"] = f"candidate exception on case {idx}\n{traceback.format_exc()}"
            return metrics, artifacts

        if not candidate_eval["valid"]:
            artifacts["error_message"] = f"candidate infeasible on case {idx}"
            return metrics, artifacts

        ratio = baseline_eval["cost"] / candidate_eval["cost"]
        total_cost += candidate_eval["cost"]
        total_ratio += ratio

    n = float(len(CASES))
    metrics["valid"] = 1.0
    metrics["num_cases"] = n
    metrics["avg_cost"] = total_cost / n
    metrics["avg_cost_ratio"] = total_ratio / n
    metrics["combined_score"] = -metrics["avg_cost"]
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    parser.add_argument("--metrics-out", default="metrics.json")
    args = parser.parse_args()

    metrics, artifacts = evaluate(args.program)
    metrics_path = Path(args.metrics_out)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if artifacts:
        Path("artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
