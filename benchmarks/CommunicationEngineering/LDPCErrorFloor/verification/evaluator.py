"""Evaluator for LDPC Error Floor estimation task.

Isolation note
--------------
The candidate is *code*, not data: this evaluator needs a live class
(``TrappingSetSampler``) whose ``sample()`` method the simulation loop calls once
per batch. There is no constant or array to lift out with ``ast.literal_eval``,
so the candidate runs in a subprocess (see
``benchmarks/_shared/sampler_isolation.py``) and hands back numbers only. Every
aggregation below -- medians, validity, score -- is computed here, in the
scoring process, from validated fields.
"""

from __future__ import annotations

import json
import math
import argparse
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np

# Frozen evaluation constants
DEV_SIGMA = 0.6
TARGET_STD = 0.1
MAX_SAMPLES = 50
BATCH_SIZE = 50
MIN_ERRORS = 20
REPEATS = 1

CODE_N = 1008
CODE_DV = 3
CODE_DC = 6

EPSILON = 2.0  # Increased tolerance for initial submissions
INVALID_SCORE_SCALE = 0.1
INVALID_SCORE_CAP = 0.1
# Reference values (calibrated from baseline under current frozen eval constants).
# With MAX_SAMPLES=50/REPEATS=1, baseline err_rate is around 1e-57 ~ 1e-48.
# Use a stable order-of-magnitude anchor instead of placeholder 1e-5 so valid metric
# is meaningful for this benchmark.
R0_DEV = 1e-56
R0_LOG_DEV = float(math.log(R0_DEV))
T0_DEV = 10.0  # Reference runtime

CANDIDATE_TIMEOUT_S = 1800.0


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _find_repo_root() -> Path:
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if _is_repo_root(candidate):
            return candidate

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            return parent
    return Path.cwd().resolve()


def _task_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _import_isolation(repo_root: Path):
    """Import the shared isolation helper.

    It lives outside every benchmark directory so a ``copy_files.txt`` of ``.``
    cannot drag it into a sandbox the candidate can write to.
    """
    shared = repo_root / "benchmarks" / "_shared"
    if not (shared / "sampler_isolation.py").is_file():
        raise RuntimeError(f"shared isolation helper not found under {shared}")
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import sampler_isolation  # noqa: PLC0415

    return sampler_isolation


def _wrap(metrics: dict[str, float], artifacts: dict[str, str | bytes]):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except ModuleNotFoundError:
        return metrics
    return EvaluationResult(metrics=metrics, artifacts=artifacts)


def _resolve_program_path(program_path: str, repo_root: Path) -> Path:
    """Resolve candidate program path robustly."""
    raw = Path(program_path).expanduser()
    if raw.is_absolute():
        return raw.resolve()

    cwd_path = (Path.cwd() / raw).resolve()
    if cwd_path.is_file():
        return cwd_path

    task_root = (
        repo_root
        / "benchmarks"
        / "CommunicationEngineering"
        / "LDPCErrorFloor"
    )
    task_path = (task_root / raw).resolve()
    return task_path


def evaluate(program_path: str, *, repo_root: Path | None = None):
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program = _resolve_program_path(program_path, repo_root)

    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "runtime_s": 0.0,
        "error_log_ratio": float("inf"),
        "valid": 0.0,
        "timeout": 0.0,
    }
    artifacts: dict[str, str | bytes] = {}

    try:
        iso = _import_isolation(repo_root)

        try:
            records = iso.run_sampler_repeats(
                task="ldpc",
                candidate_path=program,
                repo_root=repo_root,
                class_name="TrappingSetSampler",
                repeats=REPEATS,
                constants={
                    "n": CODE_N,
                    "dv": CODE_DV,
                    "dc": CODE_DC,
                    "sigma": DEV_SIGMA,
                    "target_std": TARGET_STD,
                    "max_samples": MAX_SAMPLES,
                    "batch_size": BATCH_SIZE,
                    "min_errors": MIN_ERRORS,
                },
                reset_rng=True,
                # Benchmark-owned loop: the candidate supplies sample() only, so
                # every aggregate below is produced by trusted code.
                call_mode="canonical",
                timeout_s=CANDIDATE_TIMEOUT_S,
                python=sys.executable,
            )
        except iso.SamplerRunError as e:
            if "timed out" in str(e):
                metrics["timeout"] = 1.0
            raise RuntimeError(f"加载/运行选手程序失败: {e}") from e

        runtimes: list[float] = []
        err_logs: list[float] = []
        ratios: list[float] = []
        samples: list[float] = []
        stds: list[float] = []
        converged_flags: list[float] = []

        for rep, record in enumerate(records):
            try:
                v = iso.validate_common_repeat(record, max_samples=MAX_SAMPLES)
            except iso.InvalidSubmissionError as e:
                raise ValueError(f"repeat {rep} 结果非法: {e}") from e

            errors_log = v["a"]
            weights_log = v["b"]
            err_ratio = v["c"]
            err_rate_log = float(errors_log - weights_log)

            # Handle case when no errors found (errors_log = -inf)
            if not np.isfinite(err_rate_log):
                # Use a very small error rate estimate instead of -inf
                # This allows evaluation to continue but will result in valid=0
                err_rate_log = float("-20.0")

            runtimes.append(float(v["runtime_s"]))
            err_logs.append(err_rate_log)
            ratios.append(err_ratio)
            samples.append(float(v["total_samples"]))
            stds.append(float(v["actual_std"]))
            converged_flags.append(1.0 if v["converged"] else 0.0)

        runtime_median = float(np.median(runtimes))
        err_log_median = float(np.median(err_logs))
        err_log_ratio = float(abs(err_log_median - R0_LOG_DEV))

        valid = float(err_log_ratio < EPSILON)
        raw_score = float(T0_DEV / (runtime_median * err_log_ratio + 1e-6))
        if valid > 0:
            score = raw_score
        else:
            score = min(raw_score * INVALID_SCORE_SCALE, INVALID_SCORE_CAP)

        metrics.update(
            {
                "combined_score": score,
                "runtime_s": runtime_median,
                "error_log_ratio": err_log_ratio,
                "valid": valid,
                "timeout": 0.0,
                "err_rate_log_median": err_log_median,
                "err_ratio_median": float(np.nanmedian(ratios)),
                "actual_samples_median": float(np.nanmedian(samples)),
                "actual_std_median": float(np.nanmedian(stds)),
                "converged_rate": float(np.mean(converged_flags)),
                "sigma": DEV_SIGMA,
                "isolated_candidate": 1.0,
            }
        )
        artifacts["dev_constants"] = json.dumps(
            {
                "sigma": DEV_SIGMA,
                "target_std": TARGET_STD,
                "max_samples": MAX_SAMPLES,
                "batch_size": BATCH_SIZE,
                "epsilon": EPSILON,
                "r0_dev": R0_DEV,
                "t0_dev": T0_DEV,
                "repeats": REPEATS,
                "scoring_note": (
                    "candidate runs in a subprocess and returns numbers only; "
                    "all aggregation and scoring happens in the evaluator"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        artifacts["per_repeat"] = json.dumps(
            {
                "runtime_s": runtimes,
                "err_rate_log": err_logs,
                "err_ratio": ratios,
                "actual_samples": samples,
                "actual_std": stds,
                "converged": converged_flags,
                "audit": [r["audit"] for r in records],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except (
        AttributeError,
        TypeError,
        ValueError,
        RuntimeError,
        ImportError,
        ModuleNotFoundError,
        KeyError,
    ) as e:
        metrics["combined_score"] = 0.0
        metrics["valid"] = 0.0
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = traceback.format_exc()
    finally:
        metrics["runtime_s_total"] = float(time.time() - start)

    return _wrap(metrics, artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate LDPC Error Floor submission.")
    parser.add_argument("program", help="Path to candidate program file, e.g. scripts/init.py")
    parser.add_argument("--repo-root", dest="repo_root", default=None, help="Optional repository root path.")
    parser.add_argument("--metrics-out", dest="metrics_out", default=None, help="Output metrics JSON file path.")
    args = parser.parse_args()

    repo_root = None if args.repo_root is None else Path(args.repo_root).expanduser().resolve()
    result = evaluate(args.program, repo_root=repo_root)
    if isinstance(result, dict):
        metrics = result
    else:
        metrics = result.metrics

    # Output to file if specified, otherwise stdout
    metrics_json = json.dumps(metrics, ensure_ascii=False, indent=2)
    if args.metrics_out:
        with open(args.metrics_out, 'w', encoding='utf-8') as f:
            f.write(metrics_json)
    else:
        print(metrics_json)


if __name__ == "__main__":
    main()
