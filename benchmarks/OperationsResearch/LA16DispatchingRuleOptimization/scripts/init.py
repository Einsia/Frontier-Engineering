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
    from benchmarks.OperationsResearch.LA16DispatchingRuleOptimization.baseline.solution import score_operation as _baseline_score_operation
except ModuleNotFoundError:
    from baseline.solution import score_operation as _baseline_score_operation


# EVOLVE-BLOCK-START
def score_operation(operation, state):
    return _baseline_score_operation(operation, state)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    try:
        from benchmarks.OperationsResearch.LA16DispatchingRuleOptimization.runtime.problem import load_instance, schedule_with_dispatch
    except ModuleNotFoundError:
        from runtime.problem import load_instance, schedule_with_dispatch
    instance = load_instance()
    result = schedule_with_dispatch(instance, score_operation)
    print(result["makespan"])
