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
    from benchmarks.StructuralOptimization.MBBBeamTopologyOptimization.baseline.solution import update_density as _baseline_update_density
except ModuleNotFoundError:
    from baseline.solution import update_density as _baseline_update_density


# EVOLVE-BLOCK-START
def update_density(density, sensitivity, state):
    return _baseline_update_density(density, sensitivity, state)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    try:
        from benchmarks.StructuralOptimization.MBBBeamTopologyOptimization.runtime.problem import run_optimization
    except ModuleNotFoundError:
        from runtime.problem import run_optimization

    result = run_optimization(update_density)
    print(result["compliance"])
