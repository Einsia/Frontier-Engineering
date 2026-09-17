#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _ensure_import_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            ps = str(parent)
            if ps not in sys.path:
                sys.path.insert(0, ps)
            return
    benchmark_root = here.parents[1]
    ps = str(benchmark_root)
    if ps not in sys.path:
        sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.Robotics.MultiRobotPrioritizedPlanning.baseline.solution import plan_paths as _baseline_plan_paths
except ModuleNotFoundError:
    from baseline.solution import plan_paths as _baseline_plan_paths


# EVOLVE-BLOCK-START
def plan_paths(grid, starts, goals):
    return _baseline_plan_paths(grid, starts, goals)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    try:
        from benchmarks.Robotics.MultiRobotPrioritizedPlanning.runtime.problem import GOALS, FREE_GRID, STARTS, total_cost, validate_paths
    except ModuleNotFoundError:
        from runtime.problem import GOALS, FREE_GRID, STARTS, total_cost, validate_paths

    print(total_cost(validate_paths(plan_paths(FREE_GRID, STARTS, GOALS))))
