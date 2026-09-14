#!/usr/bin/env python
"""Validate Dammann uniform-order designs and report a score in [0, 100].

The scorer supplies the grating geometry and target order range. The candidate
runs in a subprocess and returns a strictly increasing transition vector in
``submission.json``. The scorer propagates the resulting grating and computes
uniformity, efficiency and the final score. Reference designs are evaluated
with the same physical model and metrics.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.optimize import differential_evolution  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

import metrics as M  # noqa: E402
import problem as P  # noqa: E402

common = P.common
common.load_sandbox()

TASK_DIR = Path(__file__).resolve().parents[1]
DECISION_KEYS = ("transitions",)


def literature_transitions(period_size: float) -> np.ndarray:
    """Known good transitions from the diffractio advanced Dammann example."""
    x_norm = np.array(
        [
            0.0,
            0.201181,
            0.250978,
            0.326167,
            0.370555,
            0.372996,
            0.396478,
            0.453128,
            0.594731,
            0.670591,
            0.717718,
            0.890632,
            0.919921,
            0.935546,
        ],
        dtype=float,
    )
    return (x_norm - 0.5) * period_size


def optimize_transitions_de(
    prob: Dict[str, Any],
    maxiter: int = 35,
    popsize: int = 8,
    seed: int = 0,
) -> Tuple[np.ndarray, Dict[str, Any], np.ndarray, np.ndarray, float]:
    cfg = prob["cfg"]
    period_size = float(cfg["period_size"])
    n_trans = int(cfg["num_transitions"])
    n_half = n_trans // 2

    def decode(z: np.ndarray) -> np.ndarray:
        # Symmetric transition parameterization around period center.
        s = np.sort(np.clip(z, 1e-3, 1.0 - 1e-3))
        pos = 0.5 + 0.46 * s
        neg = 1.0 - pos[::-1]
        x_norm = np.concatenate([neg, pos])
        return (x_norm - 0.5) * period_size

    def objective(z: np.ndarray) -> float:
        transitions = decode(z)
        m, _, _ = M.evaluate_transitions(prob, transitions)
        base = M.loss(m)

        # Penalize too-close transitions to keep manufacturable spacing.
        min_spacing = 0.015 * period_size
        d = np.diff(np.sort(transitions))
        penalty = 100.0 * np.sum(np.clip(min_spacing - d, 0.0, None) ** 2)
        return float(base + penalty)

    bounds = [(0.02, 0.98)] * n_half
    result = differential_evolution(
        objective,
        bounds,
        maxiter=int(maxiter),
        popsize=int(popsize),
        seed=int(seed),
        polish=True,
        workers=1,
        updating="deferred",
    )

    transitions = decode(result.x)
    metrics, x_focus, intensity = M.evaluate_transitions(prob, transitions)
    return transitions, metrics, x_focus, intensity, float(result.fun)


def save_focus_plot(path: Path, x: np.ndarray, I_base: np.ndarray, I_lit: np.ndarray, I_de: np.ndarray, order_positions: np.ndarray) -> None:
    plt.figure(figsize=(8, 4))
    plt.plot(x, I_base / (I_base.max() + 1e-12), label="candidate", lw=1.8)
    plt.plot(x, I_lit / (I_lit.max() + 1e-12), label="literature", lw=1.2)
    plt.plot(x, I_de / (I_de.max() + 1e-12), label="scipy-DE", lw=1.2)
    for xp in order_positions:
        plt.axvline(xp, color="gray", ls="--", lw=0.6, alpha=0.6)
    plt.xlim(order_positions.min() - 20, order_positions.max() + 20)
    plt.xlabel("x at focus (um)")
    plt.ylabel("Normalized intensity")
    plt.title("Task03 focus profile around target diffraction orders")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def save_order_bar(path: Path, orders: np.ndarray, base_norm: np.ndarray, lit_norm: np.ndarray, de_norm: np.ndarray) -> None:
    w = 0.25
    x = np.arange(len(orders))
    plt.figure(figsize=(8, 4))
    plt.bar(x - w, base_norm, width=w, label="candidate")
    plt.bar(x, lit_norm, width=w, label="literature")
    plt.bar(x + w, de_norm, width=w, label="scipy-DE")
    plt.xticks(x, orders)
    plt.xlabel("Diffraction order m")
    plt.ylabel("Normalized order energy")
    plt.title("Task03 order energy uniformity")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def save_transition_plot(path: Path, trans_base: np.ndarray, trans_lit: np.ndarray, trans_de: np.ndarray) -> None:
    plt.figure(figsize=(8, 3.8))
    plt.plot(trans_base, np.zeros_like(trans_base), "o", label="candidate")
    plt.plot(trans_lit, np.ones_like(trans_lit), "x", label="literature")
    plt.plot(trans_de, np.full_like(trans_de, 2.0), "+", label="scipy-DE")
    plt.yticks([0, 1, 2], ["candidate", "literature", "scipy-DE"])
    plt.xlabel("Transition position in one period (um)")
    plt.title("Task03 transition comparison")
    plt.grid(True, axis="x", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Task03 validator")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "outputs")
    parser.add_argument("--candidate", type=Path, default=TASK_DIR / "baseline" / "init.py")
    parser.add_argument("--de-maxiter", type=int, default=35, help="Differential evolution maxiter")
    parser.add_argument("--de-popsize", type=int, default=8, help="Differential evolution popsize")
    parser.add_argument("--de-seed", type=int, default=0, help="Differential evolution seed")
    parser.add_argument("--candidate-timeout-s", type=float, default=common.CANDIDATE_TIMEOUT_S)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    prob = P.build_problem()
    lo, hi = P.transition_bounds(prob)

    submission, error, runtime_s = common.run_candidate(
        args.candidate,
        inputs=P.candidate_inputs(prob),
        timeout_s=args.candidate_timeout_s,
    )

    ignored_keys: list[str] = []
    trans_cand = None
    if submission is not None:
        decision, ignored_keys = common.take_decision(submission, DECISION_KEYS)
        try:
            trans_cand = common.require_transition_vector(
                decision, int(prob["cfg"]["num_transitions"]), lo, hi
            )
        except common.SubmissionError as exc:
            error = str(exc)

    if trans_cand is None:
        summary = common.invalid_summary(
            P.TASK_NAME,
            error or "candidate produced no usable transition vector",
            extra={
                "candidate_runtime_s": runtime_s,
                "ignored_submission_keys": ignored_keys,
                "valid_thresholds": M.VALID_THRESHOLDS,
            },
        )
        common.write_summary(args.output_dir, summary)
        print("[Task03] candidate rejected:", summary["candidate_error"])
        return

    metrics_base, x_base, I_base = M.evaluate_transitions(prob, trans_cand)
    score_base = metrics_base["score_pct"]

    trans_lit = literature_transitions(prob["cfg"]["period_size"])
    metrics_lit, _x_lit, I_lit = M.evaluate_transitions(prob, trans_lit)
    score_lit = metrics_lit["score_pct"]

    trans_de, metrics_de, _x_de, I_de, de_fun = optimize_transitions_de(
        prob,
        maxiter=args.de_maxiter,
        popsize=args.de_popsize,
        seed=args.de_seed,
    )
    score_de = metrics_de["score_pct"]

    if score_de >= score_lit:
        oracle_name = "scipy_differential_evolution"
        metrics_oracle = metrics_de
        score_oracle = score_de
        transitions_oracle = trans_de
    else:
        oracle_name = "literature_transition_table"
        metrics_oracle = metrics_lit
        score_oracle = score_lit
        transitions_oracle = trans_lit

    summary = {
        "task": P.TASK_NAME,
        "valid": M.is_valid(metrics_base),
        "valid_thresholds": M.VALID_THRESHOLDS,
        "contract": {
            "candidate_isolation": "subprocess, throwaway cwd, submission.json only",
            "decision_variables": list(DECISION_KEYS),
            "metrics_owner": "verification/metrics.py",
            "problem_owner": "verification/problem.py",
            "ignored_submission_keys": ignored_keys,
            "candidate_runtime_s": runtime_s,
        },
        "baseline": {
            **metrics_base,
            "score_pct": score_base,
            "transitions": trans_cand.tolist(),
        },
        "literature": {
            **metrics_lit,
            "score_pct": score_lit,
            "loss": M.loss(metrics_lit),
            "transitions": trans_lit.tolist(),
            "source": "diffractio docs/source/examples_advanced/scalar/dammann.ipynb",
        },
        "scipy_de": {
            **metrics_de,
            "score_pct": score_de,
            "loss": M.loss(metrics_de),
            "transitions": trans_de.tolist(),
            "objective_with_penalty": de_fun,
            "maxiter": int(args.de_maxiter),
            "popsize": int(args.de_popsize),
            "seed": int(args.de_seed),
        },
        "oracle": {
            **metrics_oracle,
            "score_pct": score_oracle,
            "method": "best_of_literature_and_scipy_de",
            "selected_candidate": oracle_name,
            "transitions": transitions_oracle.tolist(),
        },
        "delta": {
            "cv_improvement": float(metrics_base["cv_orders"] - metrics_oracle["cv_orders"]),
            "efficiency_gain": float(metrics_oracle["efficiency"] - metrics_base["efficiency"]),
            "score_pct_gain": float(score_oracle - score_base),
        },
    }

    common.write_summary(args.output_dir, summary)

    orders = np.asarray(metrics_base["orders"], dtype=int)
    order_pos = np.asarray(metrics_base["order_positions"], dtype=float)
    base_norm = np.asarray(metrics_base["order_energies_norm"], dtype=float)
    lit_norm = np.asarray(metrics_lit["order_energies_norm"], dtype=float)
    de_norm = np.asarray(metrics_de["order_energies_norm"], dtype=float)

    save_focus_plot(args.output_dir / "focus_profile.png", x_base, I_base, I_lit, I_de, order_pos)
    save_order_bar(args.output_dir / "order_energies.png", orders, base_norm, lit_norm, de_norm)
    save_transition_plot(args.output_dir / "transitions.png", trans_cand, trans_lit, trans_de)

    if ignored_keys:
        print("[Task03] ignored non-decision submission keys:", ", ".join(ignored_keys))
    print("[Task03] valid:", summary["valid"])
    print("[Task03] candidate  cv={:.6f}, eff={:.6f}, score_pct={:.3f}".format(
        metrics_base["cv_orders"], metrics_base["efficiency"], score_base
    ))
    print("[Task03] literature cv={:.6f}, eff={:.6f}, score_pct={:.3f}".format(
        metrics_lit["cv_orders"], metrics_lit["efficiency"], score_lit
    ))
    print("[Task03] scipy-DE   cv={:.6f}, eff={:.6f}, score_pct={:.3f}".format(
        metrics_de["cv_orders"], metrics_de["efficiency"], score_de
    ))
    print("[Task03] oracle selected candidate:", oracle_name)
    print("[Task03] outputs:", args.output_dir)


if __name__ == "__main__":
    main()
