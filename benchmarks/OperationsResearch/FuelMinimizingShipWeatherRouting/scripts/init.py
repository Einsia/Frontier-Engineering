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
    from benchmarks.OperationsResearch.FuelMinimizingShipWeatherRouting.baseline.solution import solve as _baseline_solve
    from benchmarks.OperationsResearch.FuelMinimizingShipWeatherRouting.runtime.problem import load_instance, route_metrics
except ModuleNotFoundError:
    from baseline.solution import solve as _baseline_solve
    from runtime.problem import load_instance, route_metrics


# EVOLVE-BLOCK-START
def solve(instance):
    return _baseline_solve(instance)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    result = solve(load_instance())
    print(route_metrics(result))
