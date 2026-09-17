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
    from benchmarks.OperationsResearch.LA16NeighborhoodMoveSelection.baseline.solution import MAX_ITERATIONS as _baseline_MAX_ITERATIONS, score_move as _baseline_score_move
except ModuleNotFoundError:
    from baseline.solution import MAX_ITERATIONS as _baseline_MAX_ITERATIONS, score_move as _baseline_score_move


# EVOLVE-BLOCK-START
MAX_ITERATIONS = _baseline_MAX_ITERATIONS


def score_move(move, state):
    return _baseline_score_move(move, state)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    try:
        from benchmarks.OperationsResearch.LA16NeighborhoodMoveSelection.runtime.problem import load_instance, run_local_search
    except ModuleNotFoundError:
        from runtime.problem import load_instance, run_local_search
    instance = load_instance()
    result = run_local_search(instance, score_move, MAX_ITERATIONS)
    print(result["makespan"])
