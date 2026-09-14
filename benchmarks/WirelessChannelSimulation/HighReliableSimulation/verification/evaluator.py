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

# 候选冻结常量（2026-02-15 标定结果，建议发布前再高预算复验）
DEV_SIGMA = 0.268
TARGET_STD = 0.05
MAX_SAMPLES = 100_000
BATCH_SIZE = 10_000
MIN_ERRORS = 20
REPEATS = 3
HAMMING_R = 7
CHASE_T = 3

EPSILON = 0.8
INVALID_COMBINED_SCORE = -1e18
# Re-calibrated with baseline MySampler under sigma=0.268, max_samples=10_000_000,
# 10 runs: BER uses arithmetic mean, runtime uses arithmetic mean.
R0_DEV = 7.261287772505011e-07
R0_LOG_DEV = float(math.log(R0_DEV))
T0_DEV = 10.4001037335396

CANDIDATE_TIMEOUT_S = 1800.0

# The isolation driver in benchmarks/_shared/sampler_isolation.py times each
# repeat with `time.time()`, looked up on the shared `time` module at call time.
# The candidate is executed by runpy *inside* that driver process, so rebinding
# `time.time` makes every repeat report runtime_s = 0 and the score becomes
# T0_DEV / (0 * err_log_ratio + 1e-6). Measured: combined_score 10_400_103.73
# against an honest 262.63 -- a factor of ~39_600.
#
# runtime_s feeds the score directly, so it cannot be taken on trust. This
# process measures the subprocess's wall clock itself and requires the
# self-reported total to be consistent with it. The parent's clock is in a
# different process and is not reachable from the candidate.
RUNTIME_STARTUP_ALLOWANCE_S = 5.0   # interpreter + numpy import, driver overhead
RUNTIME_MIN_FRACTION = 0.5          # of the wall clock actually spent
RUNTIME_OVERREPORT_TOLERANCE_S = 1.0


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
        from openevolve.evaluation_result import EvaluationResult  # pyright: ignore[reportMissingImports]
    except ModuleNotFoundError:
        return metrics
    return EvaluationResult(metrics=metrics, artifacts=artifacts)


def _resolve_program_path(program_path: str, repo_root: Path) -> Path:
    """
    Resolve candidate program path robustly.
    Priority:
    1) As provided (relative to current working directory).
    2) Relative to task root if (1) does not exist.
    """
    raw = Path(program_path).expanduser()
    if raw.is_absolute():
        return raw.resolve()

    cwd_path = (Path.cwd() / raw).resolve()
    if cwd_path.is_file():
        return cwd_path

    task_root = (
        repo_root
        / "benchmarks"
        / "WirelessChannelSimulation"
        / "HighReliableSimulation"
    )
    task_path = (task_root / raw).resolve()
    return task_path


def _validate_repeat_stats(
    *,
    err_rate_log: float,
    err_ratio: float,
    total_samples: float,
    actual_std: float,
) -> None:
    if not np.isfinite(err_rate_log):
        raise ValueError("err_rate_log 非有限值")
    if not np.isfinite(err_ratio) or not (0.0 <= err_ratio <= 1.0):
        raise ValueError("err_ratio 不在 [0, 1] 范围内")
    if not np.isfinite(total_samples) or total_samples <= 0:
        raise ValueError("total_samples 非法")
    if total_samples > MAX_SAMPLES:
        raise ValueError("total_samples 超过评测上限")
    if not np.isfinite(actual_std) or actual_std < 0.0:
        raise ValueError("actual_std 非法")


def evaluate(program_path: str, *, repo_root: Path | None = None):
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program = _resolve_program_path(program_path, repo_root)

    metrics: dict[str, float] = {
        "combined_score": INVALID_COMBINED_SCORE,
        "runtime_s": 0.0,
        "error_log_ratio": float("inf"),
        "valid": 0.0,
        "timeout": 0.0,
    }
    artifacts: dict[str, str | bytes] = {}

    try:
        iso = _import_isolation(repo_root)

        # The candidate is *code*: the benchmark-owned simulation loop calls the
        # candidate's sample() once per batch. It therefore runs in a subprocess
        # and returns numbers only; nothing below trusts a self-reported score.
        wall_start = time.time()
        try:
            records = iso.run_sampler_repeats(
                task="hrs",
                candidate_path=program,
                repo_root=repo_root,
                class_name="MySampler",
                repeats=REPEATS,
                constants={
                    "r": HAMMING_R,
                    "chase_t": CHASE_T,
                    "sigma": DEV_SIGMA,
                    "target_std": TARGET_STD,
                    "max_samples": MAX_SAMPLES,
                    "batch_size": BATCH_SIZE,
                    "min_errors": MIN_ERRORS,
                },
                reset_rng=True,
                call_mode="canonical",
                timeout_s=CANDIDATE_TIMEOUT_S,
                python=sys.executable,
            )
        except iso.SamplerRunError as e:
            if "timed out" in str(e):
                metrics["timeout"] = 1.0
            raise RuntimeError(f"加载选手程序失败: {e}") from e
        candidate_wall_s = float(time.time() - wall_start)

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
            _validate_repeat_stats(
                err_rate_log=err_rate_log,
                err_ratio=err_ratio,
                total_samples=float(v["total_samples"]),
                actual_std=float(v["actual_std"]),
            )

            runtimes.append(float(v["runtime_s"]))
            err_logs.append(err_rate_log)
            ratios.append(err_ratio)
            samples.append(float(v["total_samples"]))
            stds.append(float(v["actual_std"]))
            converged_flags.append(1.0 if v["converged"] else 0.0)

        # Cross-check the self-reported timings against the wall clock this
        # process measured for the whole subprocess.
        reported_total_s = float(np.sum(runtimes))
        floor_s = RUNTIME_MIN_FRACTION * max(
            0.0, candidate_wall_s - RUNTIME_STARTUP_ALLOWANCE_S
        )
        if reported_total_s > candidate_wall_s + RUNTIME_OVERREPORT_TOLERANCE_S:
            raise ValueError(
                f"自报运行时间 {reported_total_s:.3f}s 超过实测墙钟 {candidate_wall_s:.3f}s"
            )
        if reported_total_s < floor_s:
            raise ValueError(
                f"自报运行时间 {reported_total_s:.3f}s 低于墙钟下界 {floor_s:.3f}s"
                f" (wall={candidate_wall_s:.3f}s)"
            )

        runtime_median = float(np.median(runtimes))
        err_log_median = float(np.median(err_logs))
        err_log_ratio = float(abs(err_log_median - R0_LOG_DEV))
        std_median = float(np.median(stds))
        std_attainment_rate = float(np.mean(np.asarray(stds) <= TARGET_STD))

        valid = float(err_log_ratio < EPSILON and std_median <= TARGET_STD)
        raw_score = float(T0_DEV / (runtime_median * err_log_ratio + 1e-6))
        if valid > 0:
            score = raw_score
        else:
            score = INVALID_COMBINED_SCORE

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
                "actual_std_median": std_median,
                "target_std_attainment_rate": std_attainment_rate,
                "converged_rate": float(np.mean(converged_flags)),
                "sigma": DEV_SIGMA,
                "decoder_chase_t": float(CHASE_T),
                "trusted_canonical_loop": 1.0,
                "isolated_candidate": 1.0,
                "candidate_wall_s": candidate_wall_s,
                "self_reported_total_s": reported_total_s,
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
                "scoring_note": "score requires err_rate_log close to reference and median actual_std <= target_std",
                "isolation_note": (
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
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["valid"] = 0.0
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = traceback.format_exc()
    finally:
        metrics["runtime_s_total"] = float(time.time() - start)

    return _wrap(metrics, artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate HighReliableSimulation submission.")
    parser.add_argument("program", help="Path to candidate program file, e.g. scripts/init.py")
    parser.add_argument("--repo-root", dest="repo_root", default=None, help="Optional repository root path.")
    args = parser.parse_args()

    repo_root = None if args.repo_root is None else Path(args.repo_root).expanduser().resolve()
    result = evaluate(args.program, repo_root=repo_root)
    if isinstance(result, dict):
        metrics = result
    else:
        metrics = result.metrics
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
