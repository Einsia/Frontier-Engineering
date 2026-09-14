"""Evaluator for PMD Simulation task.

Isolation note
--------------
The candidate is *code*, not data: this evaluator needs a live class
(``PMDSampler``) whose ``sample()`` method is invoked once per batch inside a
simulation loop. There is nothing to lift out with ``ast.literal_eval``, so the
candidate runs in a subprocess (see
``benchmarks/_shared/sampler_isolation.py``) and returns numbers only. Medians,
validity and the score are computed here from validated fields.
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
FIBER_LENGTH_KM = 100.0
PMD_COEFFICIENT = 0.5
DGD_THRESHOLD = 30.0
TARGET_STD = 0.1
MAX_SAMPLES = 50_000
BATCH_SIZE = 5_000
MIN_OUTAGES = 20
REPEATS = 3
NUM_SEGMENTS = 100

EPSILON = 2.0  # Increased tolerance for initial submissions
INVALID_SCORE_SCALE = 0.1
INVALID_SCORE_CAP = 0.1
# Reference values (to be calibrated with baseline solution)
R0_DEV = 1e-9  # Reference outage probability (adjusted for initial testing)
R0_LOG_DEV = float(math.log(R0_DEV))
T0_DEV = 10.0

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
    task_root = repo_root / "benchmarks" / "CommunicationEngineering" / "PMDSimulation"
    return (task_root / raw).resolve()


def evaluate(program_path: str, *, repo_root: Path | None = None):
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program = _resolve_program_path(program_path, repo_root)

    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "runtime_s": 0.0,
        "outage_log_ratio": float("inf"),
        "valid": 0.0,
        "timeout": 0.0,
    }
    artifacts: dict[str, str | bytes] = {}

    try:
        iso = _import_isolation(repo_root)

        try:
            records = iso.run_sampler_repeats(
                task="pmd",
                candidate_path=program,
                repo_root=repo_root,
                class_name="PMDSampler",
                repeats=REPEATS,
                constants={
                    "fiber_length_km": FIBER_LENGTH_KM,
                    "pmd_coefficient": PMD_COEFFICIENT,
                    "num_segments": NUM_SEGMENTS,
                    "dgd_threshold": DGD_THRESHOLD,
                    "target_std": TARGET_STD,
                    "max_samples": MAX_SAMPLES,
                    "batch_size": BATCH_SIZE,
                    "min_outages": MIN_OUTAGES,
                },
                reset_rng=False,
                # NOTE: this task alone still lets the candidate own the loop.
                # The shipped baseline reimplements it (weight clipping +
                # adaptive bias), so forcing the canonical loop would change the
                # honest score. Its aggregates are therefore validated, not
                # trusted -- see the residual-risk note in the shared module.
                call_mode="candidate",
                timeout_s=CANDIDATE_TIMEOUT_S,
                python=sys.executable,
            )
        except iso.SamplerRunError as e:
            if "timed out" in str(e):
                metrics["timeout"] = 1.0
            raise RuntimeError(f"加载/运行选手程序失败: {e}") from e

        runtimes: list[float] = []
        outage_logs: list[float] = []
        probs: list[float] = []
        samples: list[float] = []
        stds: list[float] = []
        converged_flags: list[float] = []

        for rep, record in enumerate(records):
            try:
                v = iso.validate_common_repeat(record, max_samples=MAX_SAMPLES)
            except iso.InvalidSubmissionError as e:
                raise ValueError(f"repeat {rep} 结果非法: {e}") from e

            outages_log = v["a"]
            weights_log = v["b"]
            outage_prob = v["c"]
            # A probability is a probability, whatever the candidate calls it.
            if not (math.isnan(outage_prob) or 0.0 <= outage_prob <= 1.0 + 1e-6):
                raise ValueError(f"repeat {rep} 结果非法: outage_prob 不在 [0, 1] 范围内")

            outage_prob_log = float(outages_log - weights_log)

            # Handle case when no outages found (outages_log = -inf)
            if not np.isfinite(outage_prob_log):
                # Use a very small outage probability estimate instead of -inf
                outage_prob_log = float("-20.0")

            runtimes.append(float(v["runtime_s"]))
            outage_logs.append(outage_prob_log)
            probs.append(outage_prob)
            samples.append(float(v["total_samples"]))
            stds.append(float(v["actual_std"]))
            converged_flags.append(1.0 if v["converged"] else 0.0)

        runtime_median = float(np.median(runtimes))
        outage_log_median = float(np.median(outage_logs))
        outage_log_ratio = float(abs(outage_log_median - R0_LOG_DEV))

        valid = float(outage_log_ratio < EPSILON)
        raw_score = float(T0_DEV / (runtime_median * outage_log_ratio + 1e-6))
        if valid > 0:
            score = raw_score
        else:
            score = min(raw_score * INVALID_SCORE_SCALE, INVALID_SCORE_CAP)

        metrics.update({
            "combined_score": score,
            "runtime_s": runtime_median,
            "outage_log_ratio": outage_log_ratio,
            "valid": valid,
            "timeout": 0.0,
            "outage_prob_log_median": outage_log_median,
            "outage_prob_median": float(np.nanmedian(probs)),
            "actual_samples_median": float(np.nanmedian(samples)),
            "actual_std_median": float(np.nanmedian(stds)),
            "converged_rate": float(np.mean(converged_flags)),
            "dgd_threshold": DGD_THRESHOLD,
            "isolated_candidate": 1.0,
        })
        artifacts["dev_constants"] = json.dumps({
            "fiber_length_km": FIBER_LENGTH_KM,
            "pmd_coefficient": PMD_COEFFICIENT,
            "dgd_threshold": DGD_THRESHOLD,
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
        artifacts["per_repeat"] = json.dumps(
            {
                "runtime_s": runtimes,
                "outage_prob_log": outage_logs,
                "outage_prob": probs,
                "actual_samples": samples,
                "actual_std": stds,
                "converged": converged_flags,
                "audit": [r["audit"] for r in records],
            },
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
    parser = argparse.ArgumentParser(description="Evaluate PMD Simulation submission.")
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
