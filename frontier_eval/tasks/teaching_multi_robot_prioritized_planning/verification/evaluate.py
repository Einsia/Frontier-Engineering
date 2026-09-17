from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
from time import perf_counter
from types import ModuleType
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
TASK_ROOT = HERE.parent
REPO_ROOT = HERE.parents[3]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def _load_module(path: Path, module_name: str) -> ModuleType:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _benchmark_problem():
    module_path = (
        REPO_ROOT
        / "benchmarks"
        / "Robotics"
        / "MultiRobotPrioritizedPlanning"
        / "runtime"
        / "problem.py"
    )
    return _load_module(module_path, "teaching_mrpp_benchmark_problem")


def _load_solver(path: Path) -> Callable[[Any], Any]:
    module = _load_module(path, f"teaching_mrpp_{path.stem}")
    if hasattr(module, "plan_paths"):
        return getattr(module, "plan_paths")
    if hasattr(module, "solve"):
        return getattr(module, "solve")
    raise AttributeError(f"{path} must define plan_paths(grid, starts, goals) or solve(instance)")


def _evaluate_solver(label: str, solver: Callable[[Any], Any], instance: dict[str, Any]) -> dict[str, Any]:
    benchmark_problem = _benchmark_problem()
    started = perf_counter()
    try:
        try:
            result = solver(instance["grid"], instance["starts"], instance["goals"])
        except TypeError:
            result = solver(instance)
        total_cost = float(benchmark_problem.total_cost(result))
        makespan = float(benchmark_problem.makespan(result))
        valid = 1.0
        error = ""
    except Exception as exc:
        total_cost = float("inf")
        makespan = float("inf")
        valid = 0.0
        error = str(exc)
    runtime_s = perf_counter() - started
    return {
        "label": label,
        "valid": valid,
        "total_cost": total_cost,
        "makespan": makespan,
        "runtime_s": float(runtime_s),
        "error": error,
    }


def _normalized_score(candidate_cost: float, baseline_cost: float, optimum_cost: float) -> float:
    if not all(math.isfinite(x) for x in (candidate_cost, baseline_cost, optimum_cost)):
        return 0.0
    span = baseline_cost - optimum_cost
    if span <= 0:
        return 100.0 if candidate_cost <= optimum_cost else 0.0
    score = 100.0 * (baseline_cost - candidate_cost) / span
    return float(max(0.0, min(100.0, score)))


def evaluate(candidate_path: str | None = None) -> dict[str, Any]:
    benchmark_problem = _benchmark_problem()
    instance = benchmark_problem.load_instance()

    baseline_solver = _load_solver(TASK_ROOT / "baseline" / "init.py")
    reference_solver = _load_solver(HERE / "reference.py")

    baseline = _evaluate_solver("baseline", baseline_solver, instance)
    reference = _evaluate_solver("reference", reference_solver, instance)

    if candidate_path is None:
        candidate = baseline
        candidate_label = "baseline"
    else:
        candidate_label = str(Path(candidate_path).expanduser().resolve())
        try:
            candidate_solver = _load_solver(Path(candidate_path))
            candidate = _evaluate_solver("candidate", candidate_solver, instance)
        except Exception as exc:
            candidate = {
                "label": "candidate",
                "valid": 0.0,
                "total_cost": float("inf"),
                "makespan": float("inf"),
                "runtime_s": 0.0,
                "error": str(exc),
            }

    optimum_cost = reference["total_cost"] if reference["valid"] else float("inf")
    candidate_score = _normalized_score(candidate["total_cost"], baseline["total_cost"], optimum_cost)
    reference_score = _normalized_score(reference["total_cost"], baseline["total_cost"], optimum_cost)

    result: dict[str, Any] = {
        "candidate_label": candidate_label,
        "candidate_valid": candidate["valid"],
        "candidate_total_cost": candidate["total_cost"],
        "candidate_makespan": candidate["makespan"],
        "candidate_runtime_s": candidate["runtime_s"],
        "candidate_score": candidate_score,
        "baseline_valid": baseline["valid"],
        "baseline_total_cost": baseline["total_cost"],
        "baseline_makespan": baseline["makespan"],
        "baseline_runtime_s": baseline["runtime_s"],
        "baseline_score": _normalized_score(baseline["total_cost"], baseline["total_cost"], optimum_cost),
        "reference_valid": reference["valid"],
        "reference_total_cost": reference["total_cost"],
        "reference_makespan": reference["makespan"],
        "reference_runtime_s": reference["runtime_s"],
        "reference_score": reference_score,
        "lower_bound_total_cost": float(benchmark_problem.LOWER_BOUND_TOTAL_COST),
        "theoretical_optimum_total_cost": optimum_cost,
        "theoretical_upper_bound_score": 100.0,
        "combined_score": candidate_score,
    }
    if candidate["error"]:
        result["candidate_error"] = candidate["error"]
    if baseline["error"]:
        result["baseline_error"] = baseline["error"]
    if reference["error"]:
        result["reference_error"] = reference["error"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the teaching multi-robot prioritized planning scaffold.")
    parser.add_argument("candidate_path", nargs="?", default=None, help="optional candidate Python file path")
    parser.add_argument("--candidate", dest="candidate_flag", default=None, help="optional candidate Python file path")
    args = parser.parse_args(argv)
    candidate_path = args.candidate_flag or args.candidate_path
    print(json.dumps(evaluate(candidate_path), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
