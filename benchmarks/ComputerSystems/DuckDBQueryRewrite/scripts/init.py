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
    from benchmarks.ComputerSystems.DuckDBQueryRewrite.baseline.solution import rewrite_query as _baseline_rewrite_query
    from benchmarks.ComputerSystems.DuckDBQueryRewrite.runtime.problem import ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST, evaluate_query
except ModuleNotFoundError:
    from baseline.solution import rewrite_query as _baseline_rewrite_query
    from runtime.problem import ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST, evaluate_query


# EVOLVE-BLOCK-START
def rewrite_query(sql, workload_manifest):
    return _baseline_rewrite_query(sql, workload_manifest)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    print(evaluate_query(rewrite_query(ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST)))
