# EVOLVE-BLOCK-START
"""Simple greedy baseline for ORB (Applegate & Cook, 1991).

Contract (enforced by `verification/evaluate.py`):

- The evaluator runs this file in an isolated subprocess and calls
  `solve_instance(instance)` once per benchmark instance. This module is never
  imported into the scoring process, and never supplies instance data.
- `instance` is a dict with exactly three keys: `name`, `duration_matrix`,
  `machines_matrix`. There is no `metadata`: the optimum and the bounds are the
  scoring denominator and stay with the scorer.
- Return `{"machine_schedules": [...]}`, indexed by machine id, where each
  entry is `{"job_id", "operation_index", "start_time", "end_time"}`
  (`"duration"` optional). A `"makespan"` you report is only cross-checked
  against the value the scorer recomputes from the schedule; it never becomes
  the score.
- Every operation must appear exactly once, on the machine the instance
  assigns it, for exactly its stated duration, without overlapping another
  operation on the same machine or breaking the job's operation order.

Baseline constraints:
- Pure Python implementation.
- Standard library only.
- No `job_shop_lib` import and no external solver usage.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

FAMILY_PREFIX = "orb"
FAMILY_NAME = "ORB (Applegate & Cook, 1991)"


def solve_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Greedy EST+SPT scheduler on raw benchmark matrices.

    Input:
        instance dict with keys:
        - name
        - duration_matrix
        - machines_matrix

    Output:
        dict with at least:
        - machine_schedules
    """
    durations: list[list[int]] = instance["duration_matrix"]
    machines: list[list[int]] = instance["machines_matrix"]

    num_jobs = len(durations)
    total_operations = sum(len(job) for job in durations)
    num_machines = max(max(row) for row in machines) + 1

    next_op = [0] * num_jobs
    job_ready = [0] * num_jobs
    machine_ready = [0] * num_machines

    machine_schedules: list[list[dict[str, int]]] = [
        [] for _ in range(num_machines)
    ]

    scheduled = 0
    while scheduled < total_operations:
        candidates: list[tuple[int, int, int, int, int]] = []
        # (earliest_start, duration, job_id, op_idx, machine_id)
        for job_id in range(num_jobs):
            op_idx = next_op[job_id]
            if op_idx >= len(durations[job_id]):
                continue

            machine_id = machines[job_id][op_idx]
            duration = durations[job_id][op_idx]
            est = max(job_ready[job_id], machine_ready[machine_id])
            candidates.append((est, duration, job_id, op_idx, machine_id))

        if not candidates:
            raise RuntimeError("No schedulable operation found.")

        est, duration, job_id, op_idx, machine_id = min(
            candidates,
            key=lambda x: (x[0], x[1], x[2]),
        )
        end = est + duration

        machine_schedules[machine_id].append(
            {
                "job_id": job_id,
                "operation_index": op_idx,
                "start_time": est,
                "end_time": end,
                "duration": duration,
            }
        )

        next_op[job_id] += 1
        job_ready[job_id] = end
        machine_ready[machine_id] = end
        scheduled += 1

    makespan = max(job_ready) if job_ready else 0
    return {
        "makespan": makespan,
        "machine_schedules": machine_schedules,
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description=(
            f"Run the pure-python baseline on one {FAMILY_NAME} instance. "
            "The instance JSON is supplied by the evaluator; this CLI is a "
            "convenience for local debugging only."
        )
    )
    parser.add_argument(
        "--instance-json",
        required=True,
        help="Path to a JSON file with name/duration_matrix/machines_matrix.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to write the resulting schedule to.",
    )
    args = parser.parse_args()

    instance = json.loads(Path(args.instance_json).read_text(encoding="utf-8"))

    start = time.perf_counter()
    result = solve_instance(instance)
    elapsed = time.perf_counter() - start

    if args.output:
        Path(args.output).write_text(json.dumps(result), encoding="utf-8")

    print(
        f"[{FAMILY_PREFIX}] {instance.get('name', '<unnamed>')}: "
        f"makespan={result['makespan']} elapsed={elapsed:.4f}s"
    )


if __name__ == "__main__":
    _cli()
# EVOLVE-BLOCK-END
