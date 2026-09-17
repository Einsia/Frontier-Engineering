from __future__ import annotations

import argparse
import json
import math
import runpy
import traceback
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    return Path.cwd().resolve()


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_path() -> None:
    import sys

    for p in (_repo_root(), _benchmark_root()):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.ComputerSystems.DuckDBQueryRewrite.baseline.solution import rewrite_query as baseline_rewrite_query
    from benchmarks.ComputerSystems.DuckDBQueryRewrite.runtime.problem import ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST, evaluate_query
except ModuleNotFoundError:
    from baseline.solution import rewrite_query as baseline_rewrite_query
    from runtime.problem import ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST, evaluate_query


def evaluate(program_path: str):
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_runtime_s": 0.0,
        "baseline_runtime_s": 0.0,
        "row_count": 0.0,
    }
    artifacts = {}
    namespace = runpy.run_path(str(Path(program_path).expanduser().resolve()), run_name="candidate_program")
    rewrite_query = namespace.get("rewrite_query")
    if not callable(rewrite_query):
        artifacts["error_message"] = "candidate must define rewrite_query(sql, workload_manifest)"
        return metrics, artifacts
    try:
        baseline = evaluate_query(baseline_rewrite_query(ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST))
        candidate = evaluate_query(rewrite_query(ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST))
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts
    candidate_runtime = float(candidate["candidate_runtime_s"])
    baseline_runtime = float(baseline["candidate_runtime_s"])
    if not math.isfinite(candidate_runtime) or candidate_runtime <= 0:
        artifacts["error_message"] = "candidate runtime is invalid"
        return metrics, artifacts
    metrics["valid"] = 1.0
    metrics["candidate_runtime_s"] = candidate_runtime
    metrics["baseline_runtime_s"] = baseline_runtime
    metrics["row_count"] = float(candidate["row_count"])
    metrics["combined_score"] = -candidate_runtime
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    parser.add_argument("--metrics-out", default="metrics.json")
    args = parser.parse_args()
    metrics, artifacts = evaluate(args.program)
    Path(args.metrics_out).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if artifacts:
        Path("artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
