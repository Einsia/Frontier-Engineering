#!/usr/bin/env python3
"""Score a submission against the frozen Frontier-Eng Medal podium.

The corrected gold/silver/bronze baselines (2026-09-14) are shipped in
``medal_podium.csv``. This script takes a new model's best-feasible
score on each task and reports its Medal Score, so anyone can be scored against
the released benchmark without rerunning the reference models.

Usage
-----
    python leaderboard/score_submission.py <submission.csv> [--verbose]

Submission CSV format (header required): two columns, ``Task,Score``, one row
per task, using the task names from ``medal_podium.csv`` (e.g. ``JobShop_abz``).
Higher score is better on every task. Missing, blank, or nonfinite scores earn
no credit. Blank podium thresholds mean that medal tier is unavailable. See
``submission_example.csv`` (the claude-opus-4.6 column) for a working example;
scoring it reproduces its leaderboard line (Medal v1 = 0.533, v1-lite = 0.501).

Metric
------
On each task a submission earns 1.00 / 0.67 / 0.33 for reaching the gold /
silver / bronze score, else 0. The Medal Score is the mean of this credit,
normalized to [0, 1], reported on the full v1 set (47 tasks) and the v1-lite
subset (10 tasks).
"""

import argparse
import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD, SILVER, BRONZE = 1.00, 0.67, 0.33

# v1-lite: 10-task representative subset (frontier_eval/conf/batch/v1_lite.yaml).
V1_LITE = {
    "QuantumComputing_task_01_routing_qftentangled", "ComputerSystems_MallocLab",
    "JobShop_abz", "InventoryOptimization_disruption_eoqd",
    "EnergyStorage_BatteryFastChargingSPMe", "Robotics_RobotArmCycleTimeOptimization",
    "Optics_holographic_multiplane_focusing", "WirelessChannelSimulation_HighReliableSimulation",
    "ReactionOptimisation_snar_multiobjective", "StructuralOptimization_TopologyOptimization",
}


def load_podium(path):
    """task -> (gold, silver, bronze); absent thresholds are None."""
    podium = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            podium[row["Task"]] = tuple(
                float(row[name]) if row[name].strip() else None
                for name in ("Gold", "Silver", "Bronze")
            )
    return podium


def load_submission(path):
    """task -> score. Accepts a 'Task,Score' header or any two-column CSV."""
    scores = {}
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        first = next(reader, None)
        if first is None:
            return scores
        if len(first) < 2 or first[1].strip().lower() not in ("score", "best", "value"):
            f.seek(0)  # no recognizable header -> treat all rows as data
            reader = csv.reader(f)
        for row in reader:
            if len(row) < 2 or not row[0].strip():
                continue
            try:
                value = float(row[1])
            except ValueError:
                continue  # skip header/garbage rows
            if math.isfinite(value):
                scores[row[0].strip()] = value
    return scores


def tier(score, gold, silver, bronze):
    if not math.isfinite(score):
        return 0.0, None
    if gold is not None and score >= gold:
        return GOLD, "gold"
    if silver is not None and score >= silver:
        return SILVER, "silver"
    if bronze is not None and score >= bronze:
        return BRONZE, "bronze"
    return 0.0, None


def score(podium, submission, verbose=False):
    per_task = {}
    counts = {"gold": 0, "silver": 0, "bronze": 0}
    missing = []
    for task, (g, s, b) in podium.items():
        if task not in submission:
            per_task[task] = 0.0
            missing.append(task)
            continue
        pts, name = tier(submission[task], g, s, b)
        per_task[task] = pts
        if name:
            counts[name] += 1
    medal_v1 = sum(per_task.values()) / len(podium)
    lite = [t for t in podium if t in V1_LITE]
    medal_lite = sum(per_task[t] for t in lite) / len(lite)

    print(f"Medal Score (v1, 47 tasks)      : {medal_v1:.3f}"
          f"   (gold {counts['gold']}, silver {counts['silver']}, bronze {counts['bronze']})")
    print(f"Medal Score (v1-lite, 10 tasks) : {medal_lite:.3f}")
    if missing:
        print(f"\n[warn] {len(missing)} task(s) absent from submission (scored 0): "
              f"{', '.join(missing[:5])}{' ...' if len(missing) > 5 else ''}")
    if verbose:
        print("\nper-task credit:")
        for task in podium:
            print(f"  {per_task[task]:.2f}  {task}")
    return medal_v1, medal_lite


def main():
    ap = argparse.ArgumentParser(description="Score a submission against the frozen Medal podium.")
    ap.add_argument("submission", help="CSV with columns Task,Score (one row per task)")
    ap.add_argument("--podium", default=str(HERE / "medal_podium.csv"),
                    help="frozen gold/silver/bronze baselines (default: leaderboard/medal_podium.csv)")
    ap.add_argument("--verbose", action="store_true", help="print per-task medal credit")
    args = ap.parse_args()
    score(load_podium(args.podium), load_submission(args.submission), args.verbose)


if __name__ == "__main__":
    main()
