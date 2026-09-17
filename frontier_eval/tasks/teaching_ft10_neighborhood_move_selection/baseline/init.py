from __future__ import annotations

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
    from benchmarks.OperationsResearch.FT10NeighborhoodMoveSelection.runtime.problem import load_instance, run_local_search
except ModuleNotFoundError:
    from runtime.problem import load_instance, run_local_search


MAX_ITERATIONS = 50


def score_move(move, state):
    return (
        float(move["delta_duration"]),
        -float(move["machine_position"]),
        -float(move["machine_id"]),
    )


def solve(instance):
    return run_local_search(instance, score_move, MAX_ITERATIONS)


if __name__ == "__main__":
    result = solve(load_instance())
    print(result["makespan"])
