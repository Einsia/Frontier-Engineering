"""
FJSP-WF Scheduler — Agent-Editable Artifact.

Agent: only modify code between # EVOLVE-BLOCK-START and # EVOLVE-BLOCK-END.
Everything outside these markers is read-only and must not be changed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any


FAMILY = "FJSP-WF"


def _natural_key(name: str) -> list[object]:
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p for p in parts]


def _benchmark_json_path() -> Path:
    env_path = os.environ.get("FJSPWF_BENCHMARK_JSON", "").strip()
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(
            f"FJSPWF_BENCHMARK_JSON points to a missing file: {candidate}"
        )
    candidates = [
        Path(__file__).resolve().parents[1] / "data" / "benchmark_instances.json",
        Path(__file__).resolve().parents[2] / "data" / "benchmark_instances.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "benchmark_instances.json not found. "
        "Expected under FJSP-WF/data/"
    )


def load_benchmark_json() -> dict[str, dict[str, Any]]:
    with _benchmark_json_path().open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_instance_from_file(rel_path: str, base_dir: Path) -> dict[str, Any]:
    path = (base_dir / rel_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Instance file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_family_instances() -> list[dict[str, Any]]:
    data = load_benchmark_json()
    base_dir = _benchmark_json_path().parent
    instances = []
    for name, meta in data.items():
        if not name.startswith("synthetic"):
            continue
        instance = _load_instance_from_file(meta["file"], base_dir)
        instances.append(instance)
    return sorted(instances, key=lambda x: _natural_key(x["name"]))


def load_instance_by_name(name: str) -> dict[str, Any]:
    data = load_benchmark_json()
    base_dir = _benchmark_json_path().parent
    if name not in data:
        raise KeyError(f"Unknown instance: {name}")
    meta = data[name]
    return _load_instance_from_file(meta["file"], base_dir)


# EVOLVE-BLOCK-START
def solve_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Greedy EST+SPT scheduler for FJSP-WF.

    === THIS IS THE ONLY AGENT-EDITABLE FUNCTION ===
    Modify this function to improve scheduling quality.
    Do not change the function signature or output format.

    Input:
        instance dict with keys:
        - name: str
        - num_jobs: int
        - num_machines: int
        - num_workers: int
        - operations: list of dict, each with:
            - job_id: int
            - op_idx: int
            - eligible_machines: list[int]
            - processing_times: list[list[int]]  [machine_idx][worker_id]
        - worker_eligibility: list[list[int]] [worker_id] -> list of machine ids
        - metadata (optional)

    Output:
        dict with:
        - name: str
        - makespan: int
        - machine_schedules: list[list[dict]], each dict:
            - job_id, operation_index, machine_id, worker_id,
              start_time, end_time, duration
    """
    name = instance["name"]
    num_jobs = instance["num_jobs"]
    num_machines = instance["num_machines"]
    num_workers = instance["num_workers"]
    operations: list[dict[str, Any]] = instance["operations"]
    worker_eligibility: list[list[int]] = instance.get("worker_eligibility", [])

    # Build per-worker eligible machine set for fast lookup
    worker_machines: list[set[int]] = []
    for w in range(num_workers):
        if w < len(worker_eligibility):
            worker_machines.append(set(worker_eligibility[w]))
        else:
            worker_machines.append(set(range(num_machines)))

    # Group operations by job
    job_operations: list[list[dict[str, Any]]] = [[] for _ in range(num_jobs)]
    for op in operations:
        job_operations[op["job_id"]].append(op)
    for job_ops in job_operations:
        job_ops.sort(key=lambda x: x["op_idx"])

    # Track state
    next_op_idx = [0] * num_jobs
    job_ready_time = [0] * num_jobs
    machine_ready_time = [0] * num_machines
    worker_ready_time = [0] * num_workers

    machine_schedules: list[list[dict[str, Any]]] = [
        [] for _ in range(num_machines)
    ]
    total_ops = len(operations)
    scheduled = 0

    while scheduled < total_ops:
        best_candidate: tuple[int, int, int, int, int, int] | None = None

        for job_id in range(num_jobs):
            if next_op_idx[job_id] >= len(job_operations[job_id]):
                continue
            op = job_operations[job_id][next_op_idx[job_id]]
            op_idx = op["op_idx"]
            eligible_machines: list[int] = op["eligible_machines"]
            processing_times: list[list[int]] = op["processing_times"]

            for m_idx, machine_id in enumerate(eligible_machines):
                times_for_machine = processing_times[m_idx]
                for worker_id in range(num_workers):
                    if machine_id not in worker_machines[worker_id]:
                        continue
                    if worker_id >= len(times_for_machine):
                        continue
                    duration = times_for_machine[worker_id]
                    if duration <= 0:
                        continue

                    est = max(
                        job_ready_time[job_id],
                        machine_ready_time[machine_id],
                        worker_ready_time[worker_id],
                    )
                    candidate = (
                        est,
                        duration,
                        job_id,
                        op_idx,
                        machine_id,
                        worker_id,
                    )
                    if best_candidate is None or candidate < best_candidate:
                        best_candidate = candidate

        if best_candidate is None:
            raise RuntimeError("No schedulable operation found.")

        est, duration, job_id, op_idx, machine_id, worker_id = best_candidate
        end_time = est + duration

        machine_schedules[machine_id].append({
            "job_id": job_id,
            "operation_index": op_idx,
            "machine_id": machine_id,
            "worker_id": worker_id,
            "start_time": est,
            "end_time": end_time,
            "duration": duration,
        })

        next_op_idx[job_id] += 1
        job_ready_time[job_id] = end_time
        machine_ready_time[machine_id] = end_time
        worker_ready_time[worker_id] = end_time
        scheduled += 1

    makespan = max(job_ready_time) if job_ready_time else 0
    return {
        "name": name,
        "makespan": makespan,
        "machine_schedules": machine_schedules,
        "solved_by": "GreedyESTSPTBaseline",
        "family": FAMILY,
    }
# EVOLVE-BLOCK-END


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description=f"Run solver on {FAMILY} instances."
    )
    parser.add_argument(
        "--instance", type=str, default=None,
        help="Instance name. If omitted, run the first N family instances.",
    )
    parser.add_argument(
        "--max-instances", type=int, default=3,
        help="How many family instances to run when --instance is omitted.",
    )
    args = parser.parse_args()

    if args.instance:
        instances = [load_instance_by_name(args.instance)]
    else:
        instances = load_family_instances()[: max(args.max_instances, 1)]

    for instance in instances:
        start = time.perf_counter()
        result = solve_instance(instance)
        elapsed = time.perf_counter() - start
        print(
            f"[{FAMILY}] {result['name']}: "
            f"makespan={result['makespan']} elapsed={elapsed:.4f}s"
        )


if __name__ == "__main__":
    _cli()