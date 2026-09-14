"""Evaluator for Rayleigh Fading BER estimation task.

Isolation note
--------------
The candidate is *code*, not data: this evaluator needs a live class
(``DeepFadeSampler``) whose ``sample()`` method is invoked once per batch inside
a simulation loop. Nothing here can be lifted out with ``ast.literal_eval``, so
the candidate runs in a subprocess (see
``benchmarks/_shared/sampler_isolation.py``) and returns numbers only. The
internal-consistency checks below and the score are computed here.
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
SNR_DB = 10.0
TARGET_STD = 0.1
MAX_SAMPLES = 50_000
BATCH_SIZE = 5_000
MIN_ERRORS = 20
REPEATS = 3
NUM_BRANCHES = 4
SIGMA_H = 1.0
DIVERSITY_TYPE = "MRC"
MODULATION = "BPSK"

EPSILON = 2.0  # Increased tolerance for initial submissions
# Reference values (to be calibrated with baseline solution)
R0_DEV = 1e-5  # Reference BER (adjusted for initial testing)
R0_LOG_DEV = float(math.log(R0_DEV))
T0_DEV = 10.0
ERR_RATIO_REL_TOL = 1e-6
ERR_RATIO_ABS_TOL = 1e-12
INTEGER_TOL = 1e-6

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
    raw = Path(program_path).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    cwd_path = (Path.cwd() / raw).resolve()
    if cwd_path.is_file():
        return cwd_path
    task_root = repo_root / "benchmarks" / "CommunicationEngineering" / "RayleighFadingBER"
    return (task_root / raw).resolve()


def _validate_result(v: dict[str, Any]) -> dict[str, float | bool]:
    """Task-specific consistency checks on one validated repeat.

    ``v`` comes from ``sampler_isolation.validate_common_repeat`` and has already
    passed the domain checks (finiteness, integrality, sample-count bound). What
    is left is the identity that ties the three reported numbers together:
    ``err_ratio`` must equal ``exp(errors_log - weights_log)``. A candidate that
    reports an attractive BER but an inconsistent triple is rejected here.
    """
    errors_log = float(v["a"])
    weights_log = float(v["b"])
    err_ratio = float(v["c"])
    total_samples = float(v["total_samples"])
    actual_std = float(v["actual_std"])
    converged = bool(v["converged"])

    if converged and (not np.isfinite(actual_std) or actual_std > TARGET_STD + ERR_RATIO_ABS_TOL):
        raise ValueError("converged=True 但 actual_std 未达到 target_std")

    if errors_log == float("-inf"):
        if not np.isfinite(err_ratio) or not math.isclose(err_ratio, 0.0, abs_tol=ERR_RATIO_ABS_TOL):
            raise ValueError("errors_log=-inf 时 err_ratio 必须为 0")
        if converged:
            raise ValueError("未观测到错误时不应标记 converged=True")
        derived_err_ratio = 0.0
        err_rate_log = -20.0
    else:
        if not np.isfinite(errors_log):
            raise ValueError("errors_log 必须是有限值或 -inf")
        if not np.isfinite(err_ratio) or err_ratio < 0.0 or err_ratio > 1.0 + ERR_RATIO_REL_TOL:
            raise ValueError("err_ratio 必须位于 [0, 1]")
        log_ratio = errors_log - weights_log
        if log_ratio > math.log1p(ERR_RATIO_REL_TOL):
            raise ValueError("errors_log 对应的误差权重不能超过总权重")
        derived_err_ratio = float(math.exp(log_ratio))
        if not math.isclose(
            err_ratio,
            derived_err_ratio,
            rel_tol=ERR_RATIO_REL_TOL,
            abs_tol=ERR_RATIO_ABS_TOL,
        ):
            raise ValueError(
                "err_ratio 与 errors_log/weights_log 推导出的误码率不一致"
            )
        err_rate_log = float(log_ratio)

    return {
        "errors_log": errors_log,
        "weights_log": weights_log,
        "err_ratio": derived_err_ratio,
        "total_samples": total_samples,
        "actual_std": actual_std,
        "converged": converged,
        "err_rate_log": err_rate_log,
    }


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
                task="rayleigh",
                candidate_path=program,
                repo_root=repo_root,
                class_name="DeepFadeSampler",
                repeats=REPEATS,
                constants={
                    "num_branches": NUM_BRANCHES,
                    "sigma_h": SIGMA_H,
                    "diversity_type": DIVERSITY_TYPE,
                    "modulation": MODULATION,
                    "snr_db": SNR_DB,
                    "target_std": TARGET_STD,
                    "max_samples": MAX_SAMPLES,
                    "batch_size": BATCH_SIZE,
                    "min_errors": MIN_ERRORS,
                },
                reset_rng=False,
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
        repetition_diagnostics: list[dict[str, float | bool]] = []

        for rep, record in enumerate(records):
            try:
                common = iso.validate_common_repeat(
                    record,
                    max_samples=MAX_SAMPLES,
                    integer_tol=INTEGER_TOL,
                    require_bool_converged=True,
                )
            except iso.InvalidSubmissionError as e:
                raise ValueError(f"repeat {rep} 结果非法: {e}") from e

            validated = _validate_result(common)
            err_rate_log = float(validated["err_rate_log"])
            dt = float(common["runtime_s"])

            runtimes.append(dt)
            err_logs.append(err_rate_log)
            ratios.append(float(validated["err_ratio"]))
            samples.append(float(validated["total_samples"]))
            stds.append(float(validated["actual_std"]))
            converged_flags.append(1.0 if bool(validated["converged"]) else 0.0)
            repetition_diagnostics.append({
                "repeat": rep,
                "runtime_s": dt,
                "err_ratio": float(validated["err_ratio"]),
                "err_rate_log": err_rate_log,
                "total_samples": float(validated["total_samples"]),
                "actual_std": float(validated["actual_std"]),
                "converged": bool(validated["converged"]),
                "sample_calls": common["audit"]["sample_calls"],
                "proposal_rows": common["audit"]["rows"],
            })

        runtime_median = float(np.median(runtimes))
        err_log_median = float(np.median(err_logs))
        err_log_ratio = float(abs(err_log_median - R0_LOG_DEV))
        actual_std_median = float(np.nanmedian(stds))
        converged_rate = float(np.mean(converged_flags))
        variance_ok = actual_std_median <= TARGET_STD + ERR_RATIO_ABS_TOL
        convergence_ok = math.isclose(converged_rate, 1.0, abs_tol=ERR_RATIO_ABS_TOL)

        valid = float(err_log_ratio < EPSILON and variance_ok and convergence_ok)
        raw_score = float(T0_DEV / (runtime_median * err_log_ratio + 1e-6))
        score = raw_score if valid > 0 else 0.0

        metrics.update({
            "combined_score": score,
            "runtime_s": runtime_median,
            "error_log_ratio": err_log_ratio,
            "valid": valid,
            "timeout": 0.0,
            "err_rate_log_median": err_log_median,
            "err_ratio_median": float(np.nanmedian(ratios)),
            "actual_samples_median": float(np.nanmedian(samples)),
            "actual_std_median": actual_std_median,
            "converged_rate": converged_rate,
            "variance_ok": 1.0 if variance_ok else 0.0,
            "convergence_ok": 1.0 if convergence_ok else 0.0,
            "snr_db": SNR_DB,
            "isolated_candidate": 1.0,
        })
        artifacts["dev_constants"] = json.dumps({
            "snr_db": SNR_DB,
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
        }, ensure_ascii=False, indent=2)
        artifacts["replicate_diagnostics"] = json.dumps(
            repetition_diagnostics,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except (AttributeError, TypeError, ValueError, RuntimeError, ImportError, ModuleNotFoundError, KeyError) as e:
        metrics["combined_score"] = 0.0
        metrics["valid"] = 0.0
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = traceback.format_exc()
    finally:
        metrics["runtime_s_total"] = float(time.time() - start)

    return _wrap(metrics, artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Rayleigh Fading BER submission.")
    parser.add_argument("program", help="Path to candidate program file")
    parser.add_argument("--repo-root", dest="repo_root", default=None)
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
