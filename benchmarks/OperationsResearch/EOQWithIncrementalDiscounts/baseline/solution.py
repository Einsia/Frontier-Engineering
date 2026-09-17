from __future__ import annotations

import sys
from pathlib import Path


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _ensure_import_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            parent_s = str(parent)
            if parent_s not in sys.path:
                sys.path.insert(0, parent_s)
            return
    benchmark_root = here.parents[1]
    benchmark_root_s = str(benchmark_root)
    if benchmark_root_s not in sys.path:
        sys.path.insert(0, benchmark_root_s)


_ensure_import_path()

try:
    from benchmarks.OperationsResearch.EOQWithIncrementalDiscounts.runtime.problem import solve_baseline as solve
except ModuleNotFoundError:
    from runtime.problem import solve_baseline as solve
