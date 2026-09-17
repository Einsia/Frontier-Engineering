from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any


THEORETICAL_OPTIMUM_MAKESPAN = 930


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
    from benchmarks.OperationsResearch.FT10NeighborhoodMoveSelection.runtime.problem import load_instance, run_local_search
except ModuleNotFoundError:
    from runtime.problem import load_instance, run_local_search


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


def _score_from_makespan(makespan: float, baseline: float) -> float:
    if not (baseline > THEORETICAL_OPTIMUM_MAKESPAN):
        return 0.0
    if makespan is None:
        return 0.0
    span = baseline - THEORETICAL_OPTIMUM_MAKESPAN
    if span <= 0:
        return 0.0
    score = 100.0 * (baseline - float(makespan)) / span
    return max(0.0, min(100.0, score))


def _evaluate_score_module(module: ModuleType, instance: Any) -> dict[str, Any]:
    if hasattr(module, "solve"):
        result = module.solve(instance)
    else:
        score_move = getattr(module, "score_move", None)
        if score_move is None:
            raise AttributeError("candidate module must define score_move or solve")
        max_iterations = int(getattr(module, "MAX_ITERATIONS", 50))
        result = run_local_search(instance, score_move, max_iterations)
    if not isinstance(result, dict):
        raise TypeError("candidate solver must return a dict")
    if "makespan" not in result:
        raise KeyError("result missing makespan")
    return result


def evaluate(candidate_path: str | None = None) -> dict[str, Any]:
    instance = load_instance()

    baseline_module = _load_module(
        REPO_ROOT / "frontier_eval" / "tasks" / "teaching_ft10_neighborhood_move_selection" / "baseline" / "init.py",
        "teaching_ft10_baseline",
    )
    reference_module = _load_module(
        REPO_ROOT / "frontier_eval" / "tasks" / "teaching_ft10_neighborhood_move_selection" / "verification" / "reference.py",
        "teaching_ft10_reference",
    )

    baseline_start = time.perf_counter()
    baseline_result = _evaluate_score_module(baseline_module, instance)
    baseline_runtime = time.perf_counter() - baseline_start

    reference_start = time.perf_counter()
    reference_result = _evaluate_score_module(reference_module, instance)
    reference_runtime = time.perf_counter() - reference_start

    baseline_makespan = float(baseline_result["makespan"])
    reference_makespan = float(reference_result["makespan"])
    reference_score = _score_from_makespan(reference_makespan, baseline_makespan)

    metrics: dict[str, Any] = {
        "theoretical_optimum_makespan": float(THEORETICAL_OPTIMUM_MAKESPAN),
        "theoretical_upper_bound_score": 100.0,
        "baseline_makespan": baseline_makespan,
        "baseline_runtime_s": baseline_runtime,
        "baseline_score": _score_from_makespan(baseline_makespan, baseline_makespan),
        "baseline_valid": float(bool(baseline_result.get("valid", True))),
        "reference_makespan": reference_makespan,
        "reference_runtime_s": reference_runtime,
        "reference_score": reference_score,
        "reference_solver": reference_result.get("solver", "unknown"),
        "reference_valid": float(bool(reference_result.get("valid", True))),
        "valid": 1.0,
    }

    if candidate_path:
        try:
            candidate_module = _load_module(Path(candidate_path), "teaching_ft10_candidate")
            candidate_start = time.perf_counter()
            candidate_result = _evaluate_score_module(candidate_module, instance)
            candidate_runtime = time.perf_counter() - candidate_start
            candidate_makespan = float(candidate_result["makespan"])
            metrics.update(
                {
                    "candidate_makespan": candidate_makespan,
                    "candidate_runtime_s": candidate_runtime,
                    "candidate_score": _score_from_makespan(candidate_makespan, baseline_makespan),
                    "candidate_valid": float(bool(candidate_result.get("valid", True))),
                    "gap_to_optimum": candidate_makespan - THEORETICAL_OPTIMUM_MAKESPAN,
                    "combined_score": _score_from_makespan(candidate_makespan, baseline_makespan),
                }
            )
        except Exception as exc:
            metrics.update(
                {
                    "candidate_makespan": float("inf"),
                    "candidate_runtime_s": 0.0,
                    "candidate_score": 0.0,
                    "candidate_valid": 0.0,
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
                "gap_to_optimum": reference_makespan - THEORETICAL_OPTIMUM_MAKESPAN,
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
