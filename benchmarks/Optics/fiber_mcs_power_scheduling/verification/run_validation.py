#!/usr/bin/env python
"""Verification script for Task 2 (MCS + power).

The candidate no longer runs in this process. It is executed in a subprocess
whose cwd is a fresh temporary directory (see
``benchmarks/Optics/_shared/fiber_harness.py``) and hands back only
``submission.json``. That is what keeps ``verification/oracle.py`` -- the
reference-answer generator that used to sit next to the candidate on
``sys.path`` -- out of the candidate's reach.
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
    "fiber_oracle_mcs", Path(__file__).resolve().parent / "oracle.py"
)
select_mcs_power_oracle = _ORACLE.select_mcs_power_oracle

CONTRACT = harness.FiberTaskContract(
    task_name="fiber_mcs_power_scheduling",
    entrypoint="select_mcs_power",
    solution_keys=("mcs", "power_dbm"),
    tuple_kwargs=("mcs_candidates",),
    timeout_s=120.0,
)


def build_scenario(seed=123):
    rng = np.random.default_rng(seed)
    n_users = 22
    user_demands = rng.uniform(110.0, 280.0, size=n_users)
    quality_db = rng.uniform(12.0, 21.0, size=n_users)
    return {
        "user_demands_gbps": user_demands,
        "channel_quality_db": quality_db,
        "total_power_dbm": 9.0,
        "mcs_candidates": (4, 16, 64),
        "pmin_dbm": -8.0,
        "pmax_dbm": 4.0,
        "target_ber": 7e-4,
        "seed": seed,
    }


def check_valid_output(result, n_users, mcs_candidates, pmin_dbm, pmax_dbm, total_power_dbm):
    if not isinstance(result, dict):
        return False, "Output must be dict"
    if "mcs" not in result or "power_dbm" not in result:
        return False, "Missing keys mcs/power_dbm"

    mcs = np.asarray(result["mcs"])
    power_dbm = np.asarray(result["power_dbm"], dtype=float)

    if mcs.shape != (n_users,):
        return False, f"mcs shape must be {(n_users,)}"
    if power_dbm.shape != (n_users,):
        return False, f"power_dbm shape must be {(n_users,)}"

    if np.any(~np.isin(mcs, np.asarray(mcs_candidates))):
        return False, "mcs contains unsupported level"

    if np.any(power_dbm < pmin_dbm - 1e-9) or np.any(power_dbm > pmax_dbm + 1e-9):
        return False, "power out of range"

    if np.sum(10 ** (power_dbm / 10.0)) > 10 ** (total_power_dbm / 10.0) * 1.001:
        return False, "total power budget exceeded"

    return True, "ok"


def evaluate(result, scenario):
    demands = np.asarray(scenario["user_demands_gbps"], dtype=float)
    quality = np.asarray(scenario["channel_quality_db"], dtype=float)
    mcs = np.asarray(result["mcs"], dtype=int)
    p = np.asarray(result["power_dbm"], dtype=float)

    snr_db = quality + p

    ber = np.zeros_like(demands)
    achieved = np.zeros_like(demands)
    for u in range(len(demands)):
        M = int(mcs[u])
        ebn0 = snr_db[u] - 10 * np.log10(np.log2(M))
        ber[u] = float(theoryBER(M, ebn0, "qam"))
        cap = 32.0 * np.log2(M)
        reliability = 1.0 if ber[u] <= scenario["target_ber"] else np.exp(-(ber[u] - scenario["target_ber"]) * 15.0)
        achieved[u] = min(demands[u], cap * reliability)

    satisfaction = float(np.mean(np.minimum(achieved / np.maximum(demands, 1e-9), 1.0)))
    ber_pass = float(np.mean(ber <= scenario["target_ber"]))
    avg_snr = float(np.mean(snr_db))

    # weighted spectral efficiency proxy
    avg_bits = float(np.mean(np.log2(mcs)))
    se_term = np.clip(avg_bits / np.log2(max(scenario["mcs_candidates"])), 0.0, 1.0)

    score = 0.45 * satisfaction + 0.40 * ber_pass + 0.15 * se_term
    is_valid = satisfaction >= 0.40 and ber_pass >= 0.03

    return {
        "is_valid": bool(is_valid),
        "score": float(score),
        "demand_satisfaction": satisfaction,
        "ber_pass_ratio": ber_pass,
        "avg_snr_db": avg_snr,
        "avg_bits_per_symbol": avg_bits,
        "mcs": mcs.tolist(),
        "power_dbm": p.tolist(),
        "demands_gbps": demands.tolist(),
        "achieved_gbps": achieved.tolist(),
        "ber": ber.tolist(),
        "quality_db": quality.tolist(),
    }


def save_plot(cand, oracle, out_png: Path):
    q = np.asarray(cand["quality_db"])
    m_c = np.asarray(cand["mcs"])
    m_o = np.asarray(oracle["mcs"])
    a_c = np.asarray(cand["achieved_gbps"])
    a_o = np.asarray(oracle["achieved_gbps"])

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))

    ax[0].scatter(q, m_c, label="Candidate", marker="o")
    ax[0].scatter(q, m_o, label="Oracle", marker="x")
    ax[0].set_xlabel("Channel quality (dB)")
    ax[0].set_ylabel("Selected MCS order")
    ax[0].set_title("MCS decision by quality")
    ax[0].grid(alpha=0.3)
    ax[0].legend(fontsize=8)

    x = np.arange(len(a_c))
    ax[1].bar(x - 0.2, a_c, width=0.4, label="Candidate")
    ax[1].bar(x + 0.2, a_o, width=0.4, label="Oracle")
    ax[1].set_xlabel("User index")
    ax[1].set_ylabel("Achieved throughput (Gbps)")
    ax[1].set_title("Per-user achieved throughput")
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

    scenario = build_scenario(seed=123)

    harness.run_task(
        contract=CONTRACT,
        candidate_path=Path(args.solver),
        out_dir=Path(args.out_dir),
        scenario=scenario,
        check_valid_output=lambda solution: check_valid_output(
            solution,
            n_users=len(scenario["user_demands_gbps"]),
            mcs_candidates=scenario["mcs_candidates"],
            pmin_dbm=scenario["pmin_dbm"],
            pmax_dbm=scenario["pmax_dbm"],
            total_power_dbm=scenario["total_power_dbm"],
        ),
        evaluate=evaluate,
        oracle_result=lambda sc: select_mcs_power_oracle(
            **sc,
            mode=args.oracle_mode,
            time_limit_s=args.oracle_time_limit,
        ),
        save_plot=lambda cand, oracle, sc, png: save_plot(cand, oracle, png),
        plot_name="task2_verification.png",
    )


if __name__ == "__main__":
    main()
