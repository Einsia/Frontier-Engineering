#!/usr/bin/env python
"""Verification script for Task 3 (EDC/DBP mode scheduling).

``benchmarks/Optics/_shared/fiber_harness.py`` runs the candidate in a temporary
workspace and validates its returned ``submission.json``. The scorer computes
metrics and reference results separately. Filesystem protection depends on the
sandbox mode selected by the helper.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def _optics_shared_dir() -> Path:
    """Locate ``benchmarks/Optics/_shared``.

    Under the unified harness this file is a copy inside a temp sandbox, so
    walking up from ``__file__`` finds nothing; ``FRONTIER_ENGINEERING_ROOT``
    (exported by the harness, remapped under docker isolation) is the reliable
    anchor. The fallback covers running the script straight from the repo.
    """
    roots = []
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())
    roots.extend(Path(__file__).resolve().parents)
    for root in roots:
        shared = root / "benchmarks" / "Optics" / "_shared"
        if (shared / "fiber_harness.py").is_file():
            return shared
    raise RuntimeError("could not locate benchmarks/Optics/_shared")


_SHARED = _optics_shared_dir()
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import fiber_harness as harness  # noqa: E402

# Every scoring dependency is imported now, before the candidate ever runs.
from optic.comm.metrics import theoryBER  # noqa: E402

# The oracle is loaded by absolute path into *this* process only. Nothing puts
# ``verification/`` on the candidate's sys.path any more.
_ORACLE = harness.load_module_from_path(
    "fiber_oracle_dsp", Path(__file__).resolve().parent / "oracle.py"
)
choose_dsp_mode_oracle = _ORACLE.choose_dsp_mode_oracle

CONTRACT = harness.FiberTaskContract(
    task_name="fiber_dsp_mode_scheduling",
    entrypoint="choose_dsp_mode",
    solution_keys=("mode",),
    timeout_s=120.0,
)


def build_scenario(seed=7):
    rng = np.random.default_rng(seed)
    # Hard scenario by design:
    # group A: very low-SNR, low-weight, high DBP cost users
    # group B: moderate-SNR, high-weight, high-gain, low-cost users
    # group C: high-SNR users (DBP less useful)
    n_a = 8
    n_b = 8
    n_c = 8
    n_users = n_a + n_b + n_c

    est_snr_db = np.concatenate(
        [
            np.linspace(6.8, 8.4, n_a),
            np.linspace(8.6, 10.8, n_b),
            np.linspace(15.0, 20.0, n_c),
        ]
    )
    est_snr_db = est_snr_db + rng.normal(0.0, 0.06, size=n_users)

    traffic_weight = np.concatenate(
        [
            np.linspace(0.10, 0.25, n_a),
            np.linspace(12.0, 20.0, n_b),
            np.linspace(0.40, 0.90, n_c),
        ]
    )

    dbp_gain_db = np.concatenate(
        [
            np.linspace(0.10, 0.40, n_a),
            np.linspace(3.8, 6.5, n_b),
            np.linspace(0.20, 0.70, n_c),
        ]
    )

    edc_latency = np.concatenate(
        [
            np.full(n_a, 0.20e-3),
            np.full(n_b, 0.22e-3),
            np.full(n_c, 0.24e-3),
        ]
    )
    extra_latency = np.concatenate(
        [
            np.linspace(1.8e-3, 1.3e-3, n_a),
            np.linspace(0.38e-3, 0.26e-3, n_b),
            np.linspace(0.85e-3, 0.65e-3, n_c),
        ]
    )
    dbp_latency = edc_latency + extra_latency

    latency_budget = float(np.sum(edc_latency) + np.quantile(extra_latency, 0.35) * n_users * 0.27)

    user_features = {
        "est_snr_db": est_snr_db,
        "traffic_weight": traffic_weight,
        "dbp_gain_db": dbp_gain_db,
        "edc_latency_s": edc_latency,
        "dbp_latency_s": dbp_latency,
        "modulation_order": 16,
        "target_ber": 1e-3,
    }

    return {
        "user_features": user_features,
        "latency_budget_s": latency_budget,
        "max_dbp_users": 7,
        "seed": seed,
    }


def check_valid_output(result, n_users, max_dbp_users=None):
    if not isinstance(result, dict) or "mode" not in result:
        return False, "Output must be {'mode': ...}"
    try:
        mode = np.asarray(result["mode"], dtype=float)
    except Exception as exc:
        return False, f"mode 无法转换为数值数组: {exc}"
    if mode.shape != (n_users,):
        return False, f"mode shape must be {(n_users,)}"
    if np.any(~np.isfinite(mode)):
        return False, "mode must be finite"
    if np.any(mode != np.round(mode)):
        return False, "mode must contain only integer 0/1 values"
    mode = mode.astype(int)
    if np.any(~np.isin(mode, np.array([0, 1]))):
        return False, "mode must contain only 0/1"
    if max_dbp_users is not None and int(np.sum(mode)) > int(max_dbp_users):
        return False, f"DBP users exceed cap: {int(np.sum(mode))} > {int(max_dbp_users)}"
    return True, "ok"


def evaluate(result, scenario):
    mode = np.asarray(result["mode"], dtype=int)
    feat = scenario["user_features"]
    max_dbp_users = scenario.get("max_dbp_users")

    est = np.asarray(feat["est_snr_db"], dtype=float)
    gain = np.asarray(feat["dbp_gain_db"], dtype=float)
    w = np.asarray(feat["traffic_weight"], dtype=float)
    edc_t = np.asarray(feat["edc_latency_s"], dtype=float)
    dbp_t = np.asarray(feat["dbp_latency_s"], dtype=float)

    M = int(feat.get("modulation_order", 16))
    target_ber = float(feat.get("target_ber", 1e-3))

    eff_snr = est + mode * gain

    ber = np.zeros_like(eff_snr)
    utility = np.zeros_like(eff_snr)

    for i in range(len(eff_snr)):
        ebn0 = eff_snr[i] - 10 * np.log10(np.log2(M))
        ber[i] = float(theoryBER(M, ebn0, "qam"))
        rel = 1.0 if ber[i] <= target_ber else np.exp(-(ber[i] - target_ber) * 20.0)
        utility[i] = w[i] * rel

    latency = float(np.sum(np.where(mode == 1, dbp_t, edc_t)))
    budget = float(scenario["latency_budget_s"])

    ber_pass = float(np.mean(ber <= target_ber))
    weighted_utility = float(np.sum(utility) / np.sum(w))
    dbp_ratio = float(np.mean(mode))
    dbp_users = int(np.sum(mode))

    latency_over = max(0.0, (latency - budget) / max(budget, 1e-12))
    dbp_cap_ok = max_dbp_users is None or dbp_users <= int(max_dbp_users)
    latency_ok = latency <= budget * 1.001
    ber_ok = ber_pass >= 0.18

    raw_score = (
        0.65 * weighted_utility
        + 0.30 * ber_pass
        + 0.05 * (1.0 - dbp_ratio)
        - 0.70 * latency_over
    )
    is_valid = latency_ok and ber_ok and dbp_cap_ok
    constraint_violations = []
    if not latency_ok:
        constraint_violations.append("latency_budget")
    if not ber_ok:
        constraint_violations.append("min_ber_pass_ratio")
    if not dbp_cap_ok:
        constraint_violations.append("max_dbp_users")
    score = float(raw_score if is_valid else 0.0)

    return {
        "is_valid": bool(is_valid),
        "score": score,
        "raw_score": float(raw_score),
        "weighted_utility": weighted_utility,
        "ber_pass_ratio": ber_pass,
        "dbp_ratio": dbp_ratio,
        "dbp_users": dbp_users,
        "max_dbp_users": None if max_dbp_users is None else int(max_dbp_users),
        "dbp_cap_ok": bool(dbp_cap_ok),
        "latency_s": latency,
        "latency_budget_s": budget,
        "latency_ok": bool(latency_ok),
        "ber_ok": bool(ber_ok),
        "constraint_violations": constraint_violations,
        "mode": mode.tolist(),
        "effective_snr_db": eff_snr.tolist(),
        "ber": ber.tolist(),
    }


def save_plot(cand, oracle, scenario, out_png: Path):
    feat = scenario["user_features"]
    est = np.asarray(feat["est_snr_db"])

    mc = np.asarray(cand["mode"])
    mo = np.asarray(oracle["mode"])

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))

    x = np.arange(len(est))
    ax[0].plot(x, est, "k.-", label="Estimated SNR")
    ax[0].scatter(x[mc == 1], est[mc == 1], c="tab:blue", marker="o", label="Candidate DBP")
    ax[0].scatter(x[mo == 1], est[mo == 1], c="tab:red", marker="x", label="Oracle DBP")
    ax[0].set_title("Mode selection over users")
    ax[0].set_xlabel("User index")
    ax[0].set_ylabel("Estimated SNR (dB)")
    ax[0].grid(alpha=0.3)
    ax[0].legend(fontsize=8)

    labels = ["Candidate", "Oracle"]
    lat = [cand["latency_s"] * 1e3, oracle["latency_s"] * 1e3]
    bdg = scenario["latency_budget_s"] * 1e3

    ax[1].bar(labels, lat)
    ax[1].axhline(bdg, color="r", linestyle="--", label="Budget")
    ax[1].set_ylabel("Latency (ms)")
    ax[1].set_title("Total DSP latency")
    ax[1].grid(alpha=0.3)
    ax[1].legend(fontsize=8)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--solver",
        default=str(Path(__file__).resolve().parents[1] / "baseline" / "init.py"),
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parent / "outputs"),
    )
    parser.add_argument(
        "--oracle-mode",
        type=str,
        default="auto",
        choices=["auto", "exact", "heuristic"],
        help="Oracle backend mode",
    )
    parser.add_argument(
        "--oracle-time-limit",
        type=float,
        default=20.0,
        help="Oracle time budget hint (seconds)",
    )
    args = parser.parse_args()

    scenario = build_scenario(seed=7)

    harness.run_task(
        contract=CONTRACT,
        candidate_path=Path(args.solver),
        out_dir=Path(args.out_dir),
        scenario=scenario,
        check_valid_output=lambda solution: check_valid_output(
            solution,
            n_users=len(scenario["user_features"]["est_snr_db"]),
            max_dbp_users=scenario.get("max_dbp_users"),
        ),
        evaluate=evaluate,
        oracle_result=lambda sc: choose_dsp_mode_oracle(
            **sc,
            mode=args.oracle_mode,
            time_limit_s=args.oracle_time_limit,
        ),
        save_plot=save_plot,
        plot_name="task3_verification.png",
    )


if __name__ == "__main__":
    main()
