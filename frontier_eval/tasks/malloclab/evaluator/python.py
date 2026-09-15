"""Legacy task entry point for the common isolated Malloc Lab evaluator."""

from pathlib import Path
import json
import os
import sys


def evaluate(program_path: str, *, repo_root: Path | None = None):
    if repo_root is None:
        configured = os.environ.get("FRONTIER_ENGINEERING_ROOT")
        if configured:
            repo_root = Path(configured).resolve()
        else:
            repo_root = next(
                p for p in Path(__file__).resolve().parents
                if (p / "benchmarks" / "_shared" / "malloc_isolation.py").is_file()
            )
    repo_root = Path(repo_root).resolve()
    shared = repo_root / "benchmarks" / "_shared"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    from malloc_isolation import evaluate as evaluate_isolated

    metrics, artifacts = evaluate_isolated(
        Path(program_path), repo_root / "benchmarks" / "ComputerSystems" / "MallocLab"
    )
    try:
        from openevolve.evaluation_result import EvaluationResult
    except ModuleNotFoundError:
        return metrics
    return EvaluationResult(
        metrics=metrics,
        artifacts={key: value if isinstance(value, str) else json.dumps(value)
                   for key, value in artifacts.items()},
    )
