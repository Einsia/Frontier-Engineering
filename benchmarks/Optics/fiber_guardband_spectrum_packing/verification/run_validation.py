#!/usr/bin/env python
"""Verification script for Task 4 (spectrum packing + guard).

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
    "fiber_oracle_guardband", Path(__file__).resolve().parent / "oracle.py"
)
pack_spectrum_oracle = _ORACLE.pack_spectrum_oracle

CONTRACT = harness.FiberTaskContract(
    task_name="fiber_guardband_spectrum_packing",
    entrypoint="pack_spectrum",
    solution_keys=("alloc",),
    solver_kwargs=("user_demand_slots", "n_slots", "guard_slots", "seed"),
    timeout_s=120.0,
)


def build_scenario(seed=99):
    rng = np.random.default_rng(seed)
    # Bimodal demand mix:
    # many small demands + some large demands creates hard packing tradeoff.
    small = rng.integers(2, 4, size=16)
    large = rng.integers(8, 13, size=8)
    user_demand_slots = np.concatenate([small, large])
    rng.shuffle(user_demand_slots)
    user_base_snr_db = rng.uniform(16.0, 26.0, size=user_demand_slots.size)

    return {
        "user_demand_slots": user_demand_slots,
        "n_slots": 68,
        "guard_slots": 1,
        "seed": seed,
        "target_ber": 1e-3,
        "modulation_order": 16,
        "user_base_snr_db": user_base_snr_db,
    }


def check_valid_output(result, n_users):
    if not isinstance(result, dict) or "alloc" not in result:
        return False, "Output must be dict with key alloc"

    alloc = np.asarray(result["alloc"], dtype=int)
    if alloc.shape != (n_users, 2):
        return False, f"alloc shape must be {(n_users, 2)}"

    return True, "ok"


def evaluate(result, scenario):
    alloc = np.asarray(result["alloc"], dtype=int)
    demand = np.asarray(scenario["user_demand_slots"], dtype=int)
    base_snr = np.asarray(scenario["user_base_snr_db"], dtype=float)

    n_slots = int(scenario["n_slots"])
    guard = int(scenario["guard_slots"])
    target_ber = float(scenario["target_ber"])
    M = int(scenario["modulation_order"])

    # hard validity checks on geometry
    occ = np.zeros(n_slots, dtype=int)
    valid_geom = True

    for i in range(len(alloc)):
        s, w = int(alloc[i, 0]), int(alloc[i, 1])
        if s == -1 and w == 0:
            continue
        if w <= 0 or s < 0 or s + w > n_slots:
            valid_geom = False
            break
        if w != int(demand[i]):
            valid_geom = False
            break

        left = max(0, s - guard)
        right = min(n_slots, s + w + guard)
        if np.any(occ[left:right] > 0):
            valid_geom = False
            break

        occ[s : s + w] = 1

    accepted = alloc[:, 0] >= 0
    acceptance_ratio = float(np.mean(accepted))
    utilization = float(np.sum(occ) / n_slots)

    # Fragmentation: number of free blocks
    free_blocks = 0
    in_free = False
    for x in occ:
        if x == 0 and not in_free:
            free_blocks += 1
            in_free = True
        elif x == 1:
            in_free = False

    compactness = float(1.0 / (1.0 + free_blocks))

    ber = np.ones(len(alloc))
    snr_eff = np.full(len(alloc), -30.0)

    # BER proxy with adjacency interference from packed spectrum
    for i in range(len(alloc)):
        if not accepted[i]:
            continue

        s_i, w_i = int(alloc[i, 0]), int(alloc[i, 1])
        center_i = s_i + 0.5 * w_i

        interf = 0.0
        for j in range(len(alloc)):
            if i == j or not accepted[j]:
                continue
            s_j, w_j = int(alloc[j, 0]), int(alloc[j, 1])
            center_j = s_j + 0.5 * w_j
            gap = abs(center_i - center_j)
            interf += np.exp(-gap / 3.0)

        eff = base_snr[i] - 2.4 * interf
        snr_eff[i] = eff

        ebn0 = eff - 10 * np.log10(np.log2(M))
        ber[i] = float(theoryBER(M, ebn0, "qam"))

    if np.any(accepted):
        ber_pass = float(np.mean(ber[accepted] <= target_ber))
    else:
        ber_pass = 0.0

    # Put stronger emphasis on service acceptance (economic KPI) instead of pure occupancy.
    score = 0.80 * acceptance_ratio + 0.05 * utilization + 0.05 * compactness + 0.10 * ber_pass
    is_valid = bool(valid_geom and acceptance_ratio >= 0.25 and ber_pass >= 0.80)

    return {
        "is_valid": is_valid,
        "score": float(score),
        "valid_geometry": bool(valid_geom),
        "acceptance_ratio": acceptance_ratio,
        "utilization": utilization,
        "compactness": compactness,
        "ber_pass_ratio": ber_pass,
        "alloc": alloc.tolist(),
        "user_demand_slots": demand.tolist(),
        "effective_snr_db": snr_eff.tolist(),
        "ber": ber.tolist(),
    }


def save_plot(cand, oracle, scenario, out_png: Path):
    n_slots = scenario["n_slots"]
    ac = np.asarray(cand["alloc"], dtype=int)
    ao = np.asarray(oracle["alloc"], dtype=int)

    fig, axes = plt.subplots(2, 1, figsize=(12, 4.8), sharex=True)

    def draw(ax, alloc, title):
        ax.set_xlim(0, n_slots)
        ax.set_ylim(0, len(alloc) + 1)
        for i in range(len(alloc)):
            s, w = alloc[i]
            if s >= 0:
                ax.broken_barh([(s, w)], (i + 0.6, 0.8))
        ax.set_ylabel("User")
        ax.set_title(title)
        ax.grid(alpha=0.25)

    draw(axes[0], ac, "Candidate spectrum occupancy")
    draw(axes[1], ao, "Oracle spectrum occupancy")
    axes[1].set_xlabel("Spectrum slot index")

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
        choices=["auto", "hybrid", "exact_geometry", "heuristic"],
        help="Oracle backend mode",
    )
    parser.add_argument(
        "--oracle-time-limit",
        type=float,
        default=12.0,
        help="Oracle time budget hint (seconds)",
    )
    args = parser.parse_args()

    scenario = build_scenario(seed=99)

    harness.run_task(
        contract=CONTRACT,
        candidate_path=Path(args.solver),
        out_dir=Path(args.out_dir),
        scenario=scenario,
        check_valid_output=lambda solution: check_valid_output(
            solution, n_users=len(scenario["user_demand_slots"])
        ),
        evaluate=evaluate,
        oracle_result=lambda sc: pack_spectrum_oracle(
            user_demand_slots=sc["user_demand_slots"],
            n_slots=sc["n_slots"],
            guard_slots=sc["guard_slots"],
            seed=sc["seed"],
            mode=args.oracle_mode,
            time_limit_s=args.oracle_time_limit,
        ),
        save_plot=save_plot,
        plot_name="task4_verification.png",
    )


if __name__ == "__main__":
    main()
