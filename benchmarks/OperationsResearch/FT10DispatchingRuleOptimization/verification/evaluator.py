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
    from benchmarks.OperationsResearch.FT10DispatchingRuleOptimization.runtime.problem import (
        KNOWN_OPTIMUM,
        baseline_dispatch_score,
        baseline_move_score,
        load_instance,
        relative_gap,
        run_local_search,
        schedule_with_dispatch,
    )
except ModuleNotFoundError:
    from runtime.problem import (
        KNOWN_OPTIMUM,
        baseline_dispatch_score,
        baseline_move_score,
        load_instance,
        relative_gap,
        run_local_search,
        schedule_with_dispatch,
    )


TASK_KIND = "dispatch"


def evaluate(program_path: str) -> tuple[dict[str, float], dict[str, str]]:
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_makespan": 0.0,
        "baseline_makespan": 0.0,
        "relative_gap_to_optimum": 0.0,
    }
    artifacts: dict[str, str] = {}

    program = Path(program_path).expanduser().resolve()
    namespace = runpy.run_path(str(program), run_name="candidate_program")
    instance = load_instance()

    try:
        if TASK_KIND == "dispatch":
            score_fn = namespace.get("score_operation")
            if not callable(score_fn):
                raise RuntimeError("candidate must define score_operation(operation, state)")
            baseline = schedule_with_dispatch(instance, baseline_dispatch_score)
            candidate = schedule_with_dispatch(instance, score_fn)
        else:
            score_fn = namespace.get("score_move")
            if not callable(score_fn):
                raise RuntimeError("candidate must define score_move(move, state)")
            max_iterations = int(namespace.get("MAX_ITERATIONS", 50))
            baseline = run_local_search(instance, baseline_move_score, max_iterations=50)
            candidate = run_local_search(instance, score_fn, max_iterations=max_iterations)
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts

    if not baseline["valid"]:
        artifacts["error_message"] = "internal baseline produced an invalid schedule"
        return metrics, artifacts
    if not candidate["valid"]:
        artifacts["error_message"] = "candidate produced an invalid schedule"
        return metrics, artifacts

    makespan = float(candidate["makespan"])
    baseline_makespan = float(baseline["makespan"])
    if not math.isfinite(makespan) or makespan <= 0:
        artifacts["error_message"] = "candidate makespan is invalid"
        return metrics, artifacts

    metrics["valid"] = 1.0
    metrics["candidate_makespan"] = makespan
    metrics["baseline_makespan"] = baseline_makespan
    metrics["relative_gap_to_optimum"] = relative_gap(makespan, KNOWN_OPTIMUM)
    metrics["combined_score"] = -makespan
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
