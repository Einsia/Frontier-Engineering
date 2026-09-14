from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys
import traceback
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

# Never leave a __pycache__ next to the scorer. The harness fingerprints the
# readonly paths (verification/, frontier_eval/, references/) before and after
# the run, and a .pyc dropped into one of them both trips that check and, worse,
# gives a candidate a place to shadow a .py at import time. The harness exports
# PYTHONDONTWRITEBYTECODE=1 for its own runs; this covers the direct-CLI path
# too.
sys.dont_write_bytecode = True

INVALID_COMBINED_SCORE = -1e18


def _sha256(path: Path) -> str:
    """Digest of a scorer file, recorded so a tampered scorer is visible."""
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    except OSError as exc:
        return f"__unreadable__ ({exc})"


def _scorer_digests(base: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel in (
        base / "frontier_eval" / "evaluator.py",
        base / "frontier_eval" / "run_eval.py",
    ):
        if rel.is_file():
            digests[rel.name] = _sha256(rel)
    verification = base / "verification"
    if verification.is_dir():
        for path in sorted(verification.rglob("*.py")):
            digests[f"verification/{path.relative_to(verification).as_posix()}"] = _sha256(path)
    return digests


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _normalize_result(result: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if hasattr(result, "metrics") and hasattr(result, "artifacts"):
        return dict(getattr(result, "metrics")), dict(getattr(result, "artifacts"))

    if isinstance(result, dict):
        raw_metrics = result.get("metrics")
        raw_artifacts = result.get("artifacts")
        if isinstance(raw_metrics, dict):
            return dict(raw_metrics), dict(raw_artifacts or {})
        return dict(result), {}

    raise TypeError(
        "Evaluator must return an EvaluationResult-like object or a dict of metrics."
    )


def _load_local_evaluator() -> Any:
    evaluator_path = Path(__file__).with_name("evaluator.py").resolve()
    spec = spec_from_file_location("_frontier_eval_local_evaluator", evaluator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load local evaluator from {evaluator_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return getattr(module, "evaluate")
    except AttributeError as exc:
        raise RuntimeError(
            f"Local evaluator does not define evaluate(): {evaluator_path}"
        ) from exc


def _find_repo_root() -> Path:
    env_root = os.environ.get("FRONTIER_ENGINEERING_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "frontier_eval").is_dir() and (parent / "benchmarks").is_dir():
            return parent
    return Path.cwd().resolve()


def _build_kwargs(evaluate_fn: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    try:
        parameters = inspect.signature(evaluate_fn).parameters
    except Exception:
        return kwargs

    if "repo_root" in parameters:
        kwargs["repo_root"] = _find_repo_root()
    if "kernel_python" in parameters:
        kwargs["kernel_python"] = sys.executable
    return kwargs


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a benchmark-local unified evaluator and export metrics/artifacts JSON."
    )
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--metrics-out", default="metrics.json")
    parser.add_argument("--artifacts-out", default="artifacts.json")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    candidate_path = Path(args.candidate).expanduser().resolve()
    metrics_out = Path(args.metrics_out).expanduser().resolve()
    artifacts_out = Path(args.artifacts_out).expanduser().resolve()

    metrics: dict[str, Any] = {
        "combined_score": INVALID_COMBINED_SCORE,
        "valid": 0.0,
    }
    artifacts: dict[str, Any] = {
        "local_evaluator_path": str(Path(__file__).with_name("evaluator.py").resolve()),
        "candidate_path": str(candidate_path),
    }

    benchmark_dir = Path(__file__).resolve().parents[1]
    try:
        artifacts["scorer_sha256"] = json.dumps(_scorer_digests(benchmark_dir), indent=2)
    except Exception as exc:  # never let provenance bookkeeping fail a run
        artifacts["scorer_sha256_error"] = str(exc)

    try:
        evaluate_fn = _load_local_evaluator()
        result = evaluate_fn(str(candidate_path), **_build_kwargs(evaluate_fn))
        metrics, evaluator_artifacts = _normalize_result(result)
        artifacts.update(evaluator_artifacts)
    except Exception as exc:
        # Fail closed: an evaluator that raised produced no trustworthy score,
        # so the defaults above (INVALID / valid=0) are what gets written.
        metrics = {"combined_score": INVALID_COMBINED_SCORE, "valid": 0.0}
        artifacts["error_message"] = str(exc)
        artifacts["traceback"] = traceback.format_exc()

    # Backstop: a metrics dict that does not positively assert validity scores
    # as invalid. This cannot change an honest run (valid=1.0, combined_score
    # set by the evaluator); it only closes the gap where a partially-populated
    # dict would otherwise inherit the harness's optimistic defaults.
    valid = metrics.get("valid")
    if "combined_score" not in metrics or (valid is not None and float(valid) <= 0.0):
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics.setdefault("valid", 0.0)

    _write_json(metrics_out, metrics)
    _write_json(artifacts_out, artifacts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
