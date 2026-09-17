from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any


INSTANCE_PATH = Path(__file__).resolve().with_name("instance.json")
KNOWN_OPTIMUM = 945


def load_instance() -> dict[str, Any]:
    return json.loads(INSTANCE_PATH.read_text(encoding="utf-8"))


def relative_gap(value: float, optimum: float) -> float:
    return float((value - optimum) / optimum)


def baseline_dispatch_score(operation: dict[str, Any], state: dict[str, Any]):
    return (
        -float(operation["duration"]),
        -float(operation["remaining_job_work"]),
        -float(operation["job_id"]),
    )


def baseline_move_score(move: dict[str, Any], state: dict[str, Any]):
    return (
        float(move["delta_duration"]),
        -float(move["machine_position"]),
        -float(move["machine_id"]),
    )


def _build_operation_tables(instance: dict[str, Any]) -> tuple[list[list[int]], list[list[int]], dict[tuple[int, int], tuple[int, int]]]:
    durations = instance["duration_matrix"]
    machines = instance["machines_matrix"]
    op_map: dict[tuple[int, int], tuple[int, int]] = {}
    for j, row in enumerate(machines):
        for k, machine in enumerate(row):
            op_map[(j, k)] = (machine, durations[j][k])
    return durations, machines, op_map


def schedule_with_dispatch(instance: dict[str, Any], score_operation) -> dict[str, Any]:
    durations, machines, _ = _build_operation_tables(instance)
    num_jobs = len(durations)
    num_machines = len(durations[0])
    job_next = [0] * num_jobs
    job_ready = [0] * num_jobs
    machine_ready = [0] * num_machines
    scheduled_ops: list[dict[str, Any]] = []

    total_ops = num_jobs * num_machines
    while len(scheduled_ops) < total_ops:
        candidates: list[dict[str, Any]] = []
        for job_id in range(num_jobs):
            op_index = job_next[job_id]
            if op_index >= num_machines:
                continue
            machine_id = machines[job_id][op_index]
            duration = durations[job_id][op_index]
            earliest_start = max(job_ready[job_id], machine_ready[machine_id])
            remaining_job_work = sum(durations[job_id][op_index:])
            remaining_job_ops = num_machines - op_index
            candidates.append(
                {
                    "job_id": job_id,
                    "op_index": op_index,
                    "machine_id": machine_id,
                    "duration": duration,
                    "earliest_start": earliest_start,
                    "remaining_job_work": remaining_job_work,
                    "remaining_job_ops": remaining_job_ops,
                }
            )
        min_start = min(op["earliest_start"] for op in candidates)
        ready = [op for op in candidates if op["earliest_start"] == min_start]
        state = {
            "step": len(scheduled_ops),
            "job_ready_times": tuple(job_ready),
            "machine_ready_times": tuple(machine_ready),
            "current_makespan": max(max(job_ready), max(machine_ready)),
        }
        scored: list[tuple[Any, dict[str, Any]]] = []
        for op in ready:
            score = score_operation(op, state)
            scored.append((score, op))
        scored.sort(
            key=lambda item: (
                item[0],
                -item[1]["duration"],
                -item[1]["remaining_job_work"],
                -item[1]["job_id"],
            ),
            reverse=True,
        )
        chosen = scored[0][1]
        start = chosen["earliest_start"]
        end = start + chosen["duration"]
        scheduled = dict(chosen)
        scheduled["start"] = start
        scheduled["end"] = end
        scheduled_ops.append(scheduled)
        job_ready[chosen["job_id"]] = end
        machine_ready[chosen["machine_id"]] = end
        job_next[chosen["job_id"]] += 1

    return {
        "valid": True,
        "schedule": scheduled_ops,
        "makespan": max(op["end"] for op in scheduled_ops),
        "machine_sequences": machine_sequences_from_schedule(instance, scheduled_ops),
    }


def machine_sequences_from_schedule(instance: dict[str, Any], schedule: list[dict[str, Any]]) -> list[list[tuple[int, int]]]:
    num_machines = len(instance["machines_matrix"][0])
    sequences: list[list[tuple[int, int, int, int]]] = [[] for _ in range(num_machines)]
    for op in schedule:
        sequences[op["machine_id"]].append((op["start"], op["job_id"], op["op_index"], op["end"]))
    out: list[list[tuple[int, int]]] = []
    for machine_ops in sequences:
        machine_ops.sort()
        out.append([(job_id, op_index) for _, job_id, op_index, _ in machine_ops])
    return out


def build_schedule_from_machine_sequences(instance: dict[str, Any], machine_sequences: list[list[tuple[int, int]]]) -> dict[str, Any]:
    durations, machines, op_map = _build_operation_tables(instance)
    num_jobs = len(durations)
    num_machines = len(durations[0])
    machine_pred: dict[tuple[int, int], tuple[int, int] | None] = {}
    for seq in machine_sequences:
        for idx, op in enumerate(seq):
            machine_pred[op] = seq[idx - 1] if idx > 0 else None

    scheduled: dict[tuple[int, int], dict[str, Any]] = {}
    total_ops = num_jobs * num_machines
    while len(scheduled) < total_ops:
        progress = False
        for job_id in range(num_jobs):
            for op_index in range(num_machines):
                op = (job_id, op_index)
                if op in scheduled:
                    continue
                job_prev = (job_id, op_index - 1) if op_index > 0 else None
                mach_prev = machine_pred.get(op)
                if job_prev is not None and job_prev not in scheduled:
                    continue
                if mach_prev is not None and mach_prev not in scheduled:
                    continue
                machine_id, duration = op_map[op]
                start = 0
                if job_prev is not None:
                    start = max(start, scheduled[job_prev]["end"])
                if mach_prev is not None:
                    start = max(start, scheduled[mach_prev]["end"])
                scheduled[op] = {
                    "job_id": job_id,
                    "op_index": op_index,
                    "machine_id": machine_id,
                    "duration": duration,
                    "start": start,
                    "end": start + duration,
                }
                progress = True
        if not progress:
            return {"valid": False, "schedule": [], "makespan": float("inf"), "machine_sequences": machine_sequences}

    schedule = list(scheduled.values())
    schedule.sort(key=lambda item: (item["start"], item["machine_id"], item["job_id"], item["op_index"]))
    return {
        "valid": True,
        "schedule": schedule,
        "makespan": max(op["end"] for op in schedule),
        "machine_sequences": machine_sequences,
    }


def initial_machine_sequences(instance: dict[str, Any]) -> list[list[tuple[int, int]]]:
    baseline = schedule_with_dispatch(instance, baseline_dispatch_score)
    return baseline["machine_sequences"]


def generate_adjacent_moves(instance: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    durations, machines, _ = _build_operation_tables(instance)
    schedule_by_op = {
        (op["job_id"], op["op_index"]): op
        for op in current["schedule"]
    }
    moves: list[dict[str, Any]] = []
    for machine_id, seq in enumerate(current["machine_sequences"]):
        for pos in range(len(seq) - 1):
            a = seq[pos]
            b = seq[pos + 1]
            a_sched = schedule_by_op[a]
            b_sched = schedule_by_op[b]
            moves.append(
                {
                    "machine_id": machine_id,
                    "machine_position": pos,
                    "op_a": {
                        "job_id": a[0],
                        "op_index": a[1],
                        "duration": durations[a[0]][a[1]],
                        "start": a_sched["start"],
                        "end": a_sched["end"],
                    },
                    "op_b": {
                        "job_id": b[0],
                        "op_index": b[1],
                        "duration": durations[b[0]][b[1]],
                        "start": b_sched["start"],
                        "end": b_sched["end"],
                    },
                    "delta_duration": durations[a[0]][a[1]] - durations[b[0]][b[1]],
                    "current_makespan": current["makespan"],
                }
            )
    return moves


def apply_adjacent_swap(machine_sequences: list[list[tuple[int, int]]], machine_id: int, position: int) -> list[list[tuple[int, int]]]:
    new_sequences = copy.deepcopy(machine_sequences)
    new_sequences[machine_id][position], new_sequences[machine_id][position + 1] = (
        new_sequences[machine_id][position + 1],
        new_sequences[machine_id][position],
    )
    return new_sequences


def run_local_search(instance: dict[str, Any], score_move, max_iterations: int = 50) -> dict[str, Any]:
    current = schedule_with_dispatch(instance, baseline_dispatch_score)
    if not current["valid"]:
        return current

    for iteration in range(max_iterations):
        moves = generate_adjacent_moves(instance, current)
        state = {
            "iteration": iteration,
            "current_makespan": current["makespan"],
        }
        scored = []
        for move in moves:
            score = score_move(move, state)
            scored.append((score, move))
        scored.sort(
            key=lambda item: (
                item[0],
                item[1]["delta_duration"],
                -item[1]["machine_position"],
            ),
            reverse=True,
        )
        improved = False
        for _, move in scored:
            new_sequences = apply_adjacent_swap(current["machine_sequences"], move["machine_id"], move["machine_position"])
            candidate = build_schedule_from_machine_sequences(instance, new_sequences)
            if candidate["valid"] and candidate["makespan"] < current["makespan"]:
                current = candidate
                improved = True
                break
        if not improved:
            break

    return current
