#!/usr/bin/env python
"""Validation for Task 02 -- hard Fourier pattern holography, score in [0, 100].

Scoring contract (rewritten after the isolation audit)
------------------------------------------------------
1. ``verification/problem.py`` authors the aperture and the target pattern.
   The archived 99.99998936 run redefined ``target_amp`` in its own
   ``build_problem`` as the far field of a flat-phase aperture and then returned
   an all-zero phase; that is now impossible, because the target arrives from
   here as a read-only input.
2. The candidate runs as a subprocess in a throwaway directory and writes
   ``submission.json`` containing only its phase map.
3. Propagation, NMSE, energy-in-target, dark suppression and the score are all
   recomputed here from ``verification/metrics.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

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
    iterations: int = 80,
    feedback_exponent: float = 0.78,
) -> np.ndarray:
    if Hologram is None:  # pragma: no cover
        raise RuntimeError("slmsuite is required for Task02 oracle. Install: pip install slmsuite")

    target_for_opt = np.maximum(problem["target_amp"], 1e-4)

    hologram = Hologram(target=target_for_opt, amp=problem["aperture_amp"].astype(float))
    hologram.optimize(
        method="WGS-Kim",
        maxiter=int(iterations),
        verbose=False,
        feedback_exponent=float(feedback_exponent),
    )
    return np.array(hologram.get_phase())


def save_image(path: Path, image: np.ndarray, title: str, cmap: str = "inferno") -> None:
    plt.figure(figsize=(6, 5))
    plt.imshow(image, origin="lower", cmap=cmap)
    plt.colorbar()
    plt.title(title)
    plt.xlabel("x (pixel)")
    plt.ylabel("y (pixel)")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Task02 validator")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "outputs")
    parser.add_argument("--candidate", type=Path, default=TASK_DIR / "baseline" / "init.py")
    parser.add_argument("--iters", type=int, default=80, help="slmsuite WGS iterations")
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
        print("[Task02] candidate rejected:", summary["candidate_error"])
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
            "score_pct_gain": float(m_oracle["score_pct"] - m_base["score_pct"]),
            "nmse_drop": float(m_base["nmse"] - m_oracle["nmse"]),
            "energy_gain": float(m_oracle["energy_in_target"] - m_base["energy_in_target"]),
            "dark_suppression_gain": float(m_oracle["dark_suppression"] - m_base["dark_suppression"]),
        },
    }

    common.write_summary(args.output_dir, summary)

    target_intensity = prob["target_amp"] ** 2
    save_image(args.output_dir / "target_pattern.png", target_intensity, "Task02 Target Intensity", cmap="viridis")
    save_image(args.output_dir / "baseline_intensity.png", I_baseline, "Task02 Candidate Intensity")
    save_image(args.output_dir / "oracle_intensity.png", I_oracle, "Task02 Oracle Intensity (slmsuite WGS)")

    diff_base = np.abs(I_baseline / (I_baseline.mean() + 1e-12) - target_intensity / (target_intensity.mean() + 1e-12))
    diff_oracle = np.abs(I_oracle / (I_oracle.mean() + 1e-12) - target_intensity / (target_intensity.mean() + 1e-12))
    save_image(args.output_dir / "baseline_error_map.png", diff_base, "Task02 Candidate Error Map", cmap="magma")
    save_image(args.output_dir / "oracle_error_map.png", diff_oracle, "Task02 Oracle Error Map", cmap="magma")

    if ignored_keys:
        print("[Task02] ignored non-decision submission keys:", ", ".join(ignored_keys))
    print("[Task02] valid:", summary["valid"])
    print("[Task02] candidate score_pct={:.3f}, nmse={:.6f}, energy={:.6f}, dark_sup={:.6f}".format(
        m_base["score_pct"], m_base["nmse"], m_base["energy_in_target"], m_base["dark_suppression"]
    ))
    print("[Task02] oracle    score_pct={:.3f}, nmse={:.6f}, energy={:.6f}, dark_sup={:.6f}".format(
        m_oracle["score_pct"], m_oracle["nmse"], m_oracle["energy_in_target"], m_oracle["dark_suppression"]
    ))
    print("[Task02] outputs:", args.output_dir)


if __name__ == "__main__":
    main()
