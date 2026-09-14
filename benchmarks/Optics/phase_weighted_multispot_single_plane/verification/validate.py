#!/usr/bin/env python
"""Validation for Task 01 -- hard weighted multi-spot, score in [0, 1].

Scoring contract
----------------
1. This file builds the problem (``verification/problem.py``). The candidate
   never states the problem.
2. The candidate runs as a *subprocess* in a throwaway directory, reads the
   staged ``problem.npz`` / ``problem.json``, and writes ``submission.json``
   containing exactly one decision variable: the phase map.
3. Everything else -- forward propagation, spot metrics, score -- is recomputed
   here from ``verification/metrics.py``. No field the candidate reports is ever
   read into a score; ``take_decision`` drops every key but ``phase``.
4. The oracle is graded with the same functions, so candidate and oracle share
   one ruler.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

# Every import the scorer depends on happens before the candidate runs, so the
# candidate cannot supply or shadow any of it.
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

import metrics as M  # noqa: E402
import problem as P  # noqa: E402

common = P.common
common.load_sandbox()

try:  # resident before the candidate starts
    from slmsuite.holography.algorithms import Hologram
except Exception:  # pragma: no cover - reported at oracle time
    Hologram = None

TASK_DIR = Path(__file__).resolve().parents[1]
DECISION_KEYS = ("phase",)


def slmsuite_wgs_oracle(
    problem: Dict[str, Any],
    iterations: int = 70,
    feedback_exponent: float = 0.78,
) -> np.ndarray:
    if Hologram is None:  # pragma: no cover
        raise RuntimeError("slmsuite is required for Task01 oracle. Install: pip install slmsuite")

    n = len(problem["x"])
    y, x = np.indices((n, n))

    target = np.full((n, n), 0.002, dtype=float)
    for (sx, sy), w in zip(problem["spots"], problem["weights"]):
        target += np.sqrt(w) * np.exp(-((x - sx) ** 2 + (y - sy) ** 2) / (2.0 * 1.0**2))
    target = target / (target.max() + 1e-12)

    hologram = Hologram(target=target, amp=problem["aperture_amp"].astype(float))
    hologram.optimize(
        method="WGS-Kim",
        maxiter=int(iterations),
        verbose=False,
        feedback_exponent=float(feedback_exponent),
    )
    return np.array(hologram.get_phase())


def save_heatmap(path: Path, image: np.ndarray, spots: np.ndarray, title: str) -> None:
    plt.figure(figsize=(6.3, 5.4))
    plt.imshow(image, origin="lower", cmap="inferno")
    plt.colorbar(label="Intensity")
    plt.scatter(spots[:, 0], spots[:, 1], s=14, marker="o", facecolors="none", edgecolors="cyan", label="targets")
    plt.title(title)
    plt.xlabel("x (pixel)")
    plt.ylabel("y (pixel)")
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def save_ratio_scatter(path: Path, target: np.ndarray, baseline: np.ndarray, oracle: np.ndarray) -> None:
    idx = np.arange(len(target))
    plt.figure(figsize=(7.2, 4.2))
    plt.plot(idx, target, "k-", lw=1.4, label="target")
    plt.plot(idx, baseline, "o", ms=2.8, alpha=0.8, label="baseline")
    plt.plot(idx, oracle, "x", ms=2.8, alpha=0.8, label="oracle(WGS)")
    plt.xlabel("Spot index")
    plt.ylabel("Normalized spot ratio")
    plt.title("Task01 ratio distribution over dense targets")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Task01 validator")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "outputs")
    parser.add_argument("--candidate", type=Path, default=TASK_DIR / "baseline" / "init.py")
    parser.add_argument("--iters", type=int, default=70, help="slmsuite WGS iterations")
    parser.add_argument("--feedback-exponent", type=float, default=0.78, help="WGS feedback exponent")
    parser.add_argument("--candidate-timeout-s", type=float, default=common.CANDIDATE_TIMEOUT_S)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    prob = P.build_problem()

    submission, error, runtime_s = common.run_candidate(
        args.candidate,
        inputs=P.candidate_inputs(prob),
        timeout_s=args.candidate_timeout_s,
    )

    ignored_keys: list[str] = []
    phase = None
    if submission is not None:
        decision, ignored_keys = common.take_decision(submission, DECISION_KEYS)
        try:
            phase = common.require_phase_grid(decision, int(prob["cfg"]["slm_pixels"]))
        except common.SubmissionError as exc:
            error = str(exc)

    if phase is None:
        summary = common.invalid_summary(
            P.TASK_NAME,
            error or "candidate produced no usable phase map",
            extra={
                "candidate_runtime_s": runtime_s,
                "ignored_submission_keys": ignored_keys,
                "valid_thresholds": M.VALID_THRESHOLDS,
            },
        )
        common.write_summary(args.output_dir, summary)
        print("[Task01] candidate rejected:", summary["candidate_error"])
        return

    m_base, I_baseline = M.evaluate_phase(prob, phase)

    phase_oracle = slmsuite_wgs_oracle(prob, iterations=args.iters, feedback_exponent=args.feedback_exponent)
    m_oracle, I_oracle = M.evaluate_phase(prob, phase_oracle)

    summary = {
        "task": P.TASK_NAME,
        "valid": M.is_valid(m_base),
        "valid_thresholds": M.VALID_THRESHOLDS,
        "contract": {
            "candidate_isolation": "subprocess, throwaway cwd, submission.json only",
            "decision_variables": list(DECISION_KEYS),
            "metrics_owner": "verification/metrics.py",
            "problem_owner": "verification/problem.py",
            "ignored_submission_keys": ignored_keys,
            "candidate_runtime_s": runtime_s,
        },
        "baseline": m_base,
        "oracle": {
            **m_oracle,
            "method": "slmsuite WGS-Kim",
            "iterations": int(args.iters),
            "feedback_exponent": float(args.feedback_exponent),
        },
        "delta": {
            "score_gain": float(m_oracle["score"] - m_base["score"]),
            "score_pct_gain": float(m_oracle["score_pct"] - m_base["score_pct"]),
            "efficiency_gain": float(m_oracle["efficiency"] - m_base["efficiency"]),
            "ratio_mae_drop": float(m_base["ratio_mae"] - m_oracle["ratio_mae"]),
            "cv_drop": float(m_base["cv_spots"] - m_oracle["cv_spots"]),
        },
    }

    common.write_summary(args.output_dir, summary)

    save_heatmap(args.output_dir / "baseline_intensity.png", I_baseline, prob["spots"], "Task01 Candidate Intensity")
    save_heatmap(args.output_dir / "oracle_intensity.png", I_oracle, prob["spots"], "Task01 Oracle Intensity (slmsuite WGS)")
    save_ratio_scatter(
        args.output_dir / "spot_ratios.png",
        np.asarray(m_base["target_ratios"]),
        np.asarray(m_base["spot_ratios"]),
        np.asarray(m_oracle["spot_ratios"]),
    )

    if ignored_keys:
        print("[Task01] ignored non-decision submission keys:", ", ".join(ignored_keys))
    print("[Task01] valid:", summary["valid"])
    print("[Task01] candidate score={:.4f}, ratio_mae={:.6f}, cv={:.6f}, eff={:.6f}".format(
        m_base["score"], m_base["ratio_mae"], m_base["cv_spots"], m_base["efficiency"]
    ))
    print("[Task01] oracle    score={:.4f}, ratio_mae={:.6f}, cv={:.6f}, eff={:.6f}".format(
        m_oracle["score"], m_oracle["ratio_mae"], m_oracle["cv_spots"], m_oracle["efficiency"]
    ))
    print("[Task01] outputs:", args.output_dir)


if __name__ == "__main__":
    main()
