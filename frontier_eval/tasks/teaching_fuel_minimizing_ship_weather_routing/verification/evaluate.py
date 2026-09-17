from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def _ensure_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            root = parent
            root_s = str(root)
            if root_s not in sys.path:
                sys.path.insert(0, root_s)
            return root
    raise RuntimeError("could not locate repository root")


REPO_ROOT = _ensure_repo_root()

try:
    from benchmarks.OperationsResearch.FuelMinimizingShipWeatherRouting.runtime.problem import (
        REFERENCE_FUEL,
        REFERENCE_TIME_H,
        BASELINE_FUEL,
        BASELINE_TIME_H,
        load_instance,
        route_metrics,
        validate_path,
    )
except ModuleNotFoundError:
    from runtime.problem import REFERENCE_FUEL, REFERENCE_TIME_H, BASELINE_FUEL, BASELINE_TIME_H, load_instance, route_metrics, validate_path


def _load_module(path: Path, module_name: str) -> ModuleType:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _score_from_fuel(fuel: float, baseline: float, optimum: float) -> float:
    if not (baseline > optimum):
        return 0.0
    span = baseline - optimum
    if span <= 0:
        return 0.0
    score = 100.0 * (baseline - float(fuel)) / span
    return max(0.0, min(100.0, score))


def _evaluate_solve_module(module: ModuleType, instance: Any) -> dict[str, Any]:
    if not hasattr(module, "solve"):
        raise AttributeError("candidate module must define solve")
    result = module.solve(instance)
    path = validate_path(result)
    metrics = route_metrics(path)
    return {"path": path, **metrics}


def evaluate(candidate_path: str | None = None) -> dict[str, Any]:
    instance = load_instance()

    baseline_module = _load_module(
        REPO_ROOT / "frontier_eval" / "tasks" / "teaching_fuel_minimizing_ship_weather_routing" / "baseline" / "init.py",
        "teaching_fuel_baseline",
    )
    reference_module = _load_module(
        REPO_ROOT / "frontier_eval" / "tasks" / "teaching_fuel_minimizing_ship_weather_routing" / "verification" / "reference.py",
        "teaching_fuel_reference",
    )

    baseline_result = _evaluate_solve_module(baseline_module, instance)
    reference_result = _evaluate_solve_module(reference_module, instance)
    baseline_fuel = float(baseline_result["fuel"])
    reference_fuel = float(reference_result["fuel"])
    optimum_fuel = reference_fuel
    reference_score = _score_from_fuel(reference_fuel, baseline_fuel, optimum_fuel)

    metrics: dict[str, Any] = {
        "baseline_fuel": baseline_fuel,
        "baseline_time_h": float(baseline_result["time_h"]),
        "baseline_hops": float(baseline_result["hops"]),
        "reference_fuel": reference_fuel,
        "reference_time_h": float(reference_result["time_h"]),
        "reference_hops": float(reference_result["hops"]),
        "theoretical_optimum_fuel": float(optimum_fuel),
        "theoretical_optimum_time_h": float(REFERENCE_TIME_H),
        "theoretical_upper_bound_score": 100.0,
        "baseline_score": _score_from_fuel(baseline_fuel, baseline_fuel, optimum_fuel),
        "reference_score": reference_score,
        "valid": 1.0,
    }

    if candidate_path:
        try:
            candidate_module = _load_module(Path(candidate_path), "teaching_fuel_candidate")
            candidate_result = _evaluate_solve_module(candidate_module, instance)
            candidate_fuel = float(candidate_result["fuel"])
            metrics.update(
                {
                    "candidate_fuel": candidate_fuel,
                    "candidate_time_h": float(candidate_result["time_h"]),
                    "candidate_hops": float(candidate_result["hops"]),
                    "candidate_score": _score_from_fuel(candidate_fuel, baseline_fuel, optimum_fuel),
                    "gap_to_optimum": candidate_fuel - optimum_fuel,
                    "combined_score": _score_from_fuel(candidate_fuel, baseline_fuel, optimum_fuel),
                }
            )
        except Exception as exc:
            metrics.update(
                {
                    "candidate_fuel": float("inf"),
                    "candidate_time_h": float("inf"),
                    "candidate_hops": float("inf"),
                    "candidate_score": 0.0,
                    "gap_to_optimum": float("inf"),
                    "combined_score": 0.0,
                    "valid": 0.0,
                    "candidate_error": str(exc),
                }
            )
    else:
        metrics.update(
            {
                "combined_score": reference_score,
                "gap_to_optimum": reference_fuel - optimum_fuel,
            }
        )

    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_path", nargs="?", default=None)
    parser.add_argument("--candidate", dest="candidate_flag", default=None)
    args = parser.parse_args(argv)
    candidate_path = args.candidate_flag or args.candidate_path
    metrics = evaluate(candidate_path)
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
