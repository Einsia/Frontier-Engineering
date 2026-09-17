from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_repo_root() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            root = str(parent)
            if root not in sys.path:
                sys.path.insert(0, root)
            return


_ensure_repo_root()

try:
    from benchmarks.OperationsResearch.FT10NeighborhoodMoveSelection.runtime.problem import (
        build_schedule_from_machine_sequences,
        load_instance,
    )
except ModuleNotFoundError:
    from runtime.problem import (
        build_schedule_from_machine_sequences,
        load_instance,
    )


try:  # pragma: no cover - optional dependency
    from job_shop_lib.benchmarking import load_benchmark_instance
    from job_shop_lib.constraint_programming import ORToolsSolver
except Exception as exc:  # pragma: no cover - environment dependent
    JOB_SHOP_LIB_IMPORT_ERROR = exc
    ORToolsSolver = None
    load_benchmark_instance = None
else:  # pragma: no cover - environment dependent
    JOB_SHOP_LIB_IMPORT_ERROR = None


EXTERNAL_TIME_LIMIT_S = float(os.environ.get("TEACHING_FT10_REFERENCE_TIME_LIMIT", "20.0"))
ENABLE_EXTERNAL_SOLVER = os.environ.get("TEACHING_FT10_ENABLE_ORTOOLS", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# This machine order was extracted from a 20-second OR-Tools CP-SAT run on ft10.
# It gives makespan 938 when replayed through the local runtime helpers.
EMBEDDED_REFERENCE_MACHINE_SEQUENCES = [
    [(1, 0), (4, 1), (6, 1), (8, 0), (7, 1), (3, 2), (9, 1), (0, 0), (2, 1), (5, 6)],
    [(6, 0), (3, 0), (4, 2), (9, 0), (8, 1), (1, 5), (5, 1), (2, 0), (7, 2), (0, 1)],
    [(4, 0), (7, 0), (1, 1), (3, 1), (6, 3), (5, 0), (9, 2), (8, 4), (0, 2), (2, 3)],
    [(6, 2), (4, 4), (1, 4), (8, 2), (5, 3), (2, 2), (0, 3), (9, 7), (3, 7), (7, 9)],
    [(1, 2), (4, 5), (3, 3), (7, 4), (0, 4), (6, 9), (8, 8), (9, 8), (5, 8), (2, 9)],
    [(4, 3), (6, 5), (5, 2), (8, 3), (1, 7), (7, 3), (9, 6), (0, 5), (2, 5), (3, 9)],
    [(6, 4), (1, 6), (3, 4), (9, 3), (4, 9), (8, 6), (7, 5), (0, 6), (2, 7), (5, 7)],
    [(4, 7), (6, 8), (3, 6), (1, 8), (8, 7), (2, 6), (0, 7), (7, 8), (9, 9), (5, 9)],
    [(4, 6), (6, 7), (3, 5), (9, 4), (5, 4), (2, 4), (7, 6), (8, 9), (0, 8), (1, 9)],
    [(1, 3), (6, 6), (4, 8), (8, 5), (9, 5), (5, 5), (7, 7), (3, 8), (2, 8), (0, 9)],
]


def _solve_from_machine_sequences(instance):
    result = build_schedule_from_machine_sequences(instance, EMBEDDED_REFERENCE_MACHINE_SEQUENCES)
    if result["valid"]:
        result["solver"] = "embedded_cp_sat_machine_order"
    return result


def _solve_with_ortools(instance):
    if ORToolsSolver is None or load_benchmark_instance is None:
        raise RuntimeError(f"external solver unavailable: {JOB_SHOP_LIB_IMPORT_ERROR}")
    solver = ORToolsSolver(
        max_time_in_seconds=EXTERNAL_TIME_LIMIT_S,
        log_search_progress=False,
    )
    schedule = solver(load_benchmark_instance("ft10"))
    machine_sequences = []
    for machine_ops in schedule.schedule:
        sequence = []
        for scheduled_op in machine_ops:
            op = scheduled_op.operation
            sequence.append((int(op.job_id), int(op.position_in_job)))
        machine_sequences.append(sequence)
    result = build_schedule_from_machine_sequences(instance, machine_sequences)
    if result["valid"]:
        result["solver"] = "ortools_cp_sat"
        result["ortools_status"] = str(schedule.metadata.get("status", "unknown"))
        result["ortools_time_limit_s"] = EXTERNAL_TIME_LIMIT_S
    return result


def solve(instance):
    best = _solve_from_machine_sequences(instance)
    if not ENABLE_EXTERNAL_SOLVER:
        return best
    if ORToolsSolver is None or load_benchmark_instance is None:
        return best

    try:  # pragma: no cover - environment dependent
        candidate = _solve_with_ortools(instance)
    except Exception as exc:
        best["external_solver_error"] = str(exc)
        return best

    if candidate["valid"] and candidate["makespan"] <= best["makespan"]:
        return candidate
    return best


def best_run_makespan(instance):
    return solve(instance)["makespan"]


if __name__ == "__main__":
    print(best_run_makespan(load_instance()))
