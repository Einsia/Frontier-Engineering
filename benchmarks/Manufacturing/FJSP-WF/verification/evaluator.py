"""
FJSP-WF Evaluator  - ad-only scoring script.

Supports two instance formats:
  .fjs  : Official GECCO FJSSP-WU Competition format (1-based indices)
  .fjswf: Benchmark JSON format (0-based indices)

Both formats produce the same internal dict representation.

Usage:
    python verification/evaluator.py scripts/init.py
    python verification/evaluator.py scripts/init.py --instances mk01
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import numbers
import subprocess
import os
import pathlib
import re
import statistics
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


FAMILY = "FJSP-WF"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class InstanceResult:
    name: str
    num_jobs: int
    num_machines: int
    num_workers: int
    total_operations: int
    baseline_makespan: int | None
    baseline_valid: bool
    baseline_note: str | None
    baseline_elapsed_s: float
    agent_makespan: int | None
    agent_valid: bool
    agent_note: str | None
    agent_elapsed_s: float
    score: float | None


@dataclass
class ScheduleValidation:
    valid: bool
    actual_makespan: int
    note: str | None
    errors: list[str]


# ---------------------------------------------------------------------------
# FJS format parser (official GECCO FJSSP-WU Competition format)
# ---------------------------------------------------------------------------

def parse_fjs_file(path: Path) -> dict[str, Any]:
    """Parse an official .fjs instance file into the benchmark's internal dict format.

    The .fjs format is:
      Line 0: [num_jobs] [num_machines] [num_workers]
      Lines 1+: one line per job
        [n_operations_in_job]
          [For each op]: [n_machine_options]
            [machine_id(1)] [n_worker_options] [worker_id(1), duration] ...
            [machine_id(2)] [n_worker_options] [worker_id(1), duration] ...

    Internal format (0-based):
      operations[i] = {job_id, op_idx, eligible_machines, processing_times}
        eligible_machines[m_idx] = machine_id (0-based)
        processing_times[m_idx][w] = duration (0 = unavailable combination)
      worker_eligibility[w] = sorted list of machine_ids worker can operate
    """
    with path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    header = list(map(int, lines[0].split()))
    num_jobs = header[0]
    num_machines = header[1]
    num_workers = header[2]

    all_operations: list[dict[str, Any]] = []
    worker_machine_pairs: set[tuple[int, int]] = set()

    for job_idx, line in enumerate(lines[1:]):
        vals = list(map(int, line.split()))
        idx = 0
        n_ops_in_job = vals[idx]
        idx += 1

        for op_idx_in_job in range(n_ops_in_job):
            n_mach_opts = vals[idx]
            idx += 1
            eligible: set[int] = set()
            pt_rows: dict[int, dict[int, int]] = {}

            for _ in range(n_mach_opts):
                machine = vals[idx] - 1  # 1-based -> 0-based
                idx += 1
                n_worker_opts = vals[idx]
                idx += 1
                eligible.add(machine)

                if machine not in pt_rows:
                    pt_rows[machine] = {}

                for _ in range(n_worker_opts):
                    worker = vals[idx] - 1  # 1-based -> 0-based
                    idx += 1
                    duration = vals[idx]
                    idx += 1
                    pt_rows[machine][worker] = duration
                    worker_machine_pairs.add((worker, machine))

            eligible_list = sorted(eligible)
            pt_matrix: list[list[int]] = []
            for m in eligible_list:
                row = [0] * num_workers
                for w, d in pt_rows.get(m, {}).items():
                    row[w] = d
                pt_matrix.append(row)

            all_operations.append({
                "job_id": job_idx,
                "op_idx": op_idx_in_job,
                "eligible_machines": eligible_list,
                "processing_times": pt_matrix,
            })

    # Build worker_eligibility from all observed (worker, machine) pairs
    worker_elig: list[list[int]] = [[] for _ in range(num_workers)]
    for worker, machine in sorted(worker_machine_pairs):
        if machine not in worker_elig[worker]:
            worker_elig[worker].append(machine)

    return {
        "name": path.stem,
        "description": f"FJSSP-W instance: {num_jobs} jobs, {num_machines} machines, {num_workers} workers",
        "num_jobs": num_jobs,
        "num_machines": num_machines,
        "num_workers": num_workers,
        "operations": all_operations,
        "worker_eligibility": worker_elig,
        "metadata": {
            "best_known_makespan": None,
            "lower_bound": None,
            "source": "GECCO FJSSP-WU Competition (Apache-2.0)",
            "file_format": "fjs",
        },
    }


# ---------------------------------------------------------------------------
# Module loading and instance resolution
# ---------------------------------------------------------------------------


def _run_candidate_subprocess(candidate_path, instance):
    """Run candidate solver in subprocess, return (result_dict_or_None, error_msg_or_None)."""
    runner_path = Path(__file__).parent / '_candidate_runner.py'
    
    try:
        proc = subprocess.run(
            [sys.executable, str(runner_path), str(candidate_path)],
            input=json.dumps(instance),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return None, 'subprocess timed out (300s)'
    except Exception as exc:
        return None, f'subprocess failed to launch: {exc}'
    
    if proc.returncode != 0:
        try:
            err_data = json.loads(proc.stdout) if proc.stdout.strip() else {}
            err_msg = err_data.get('error', proc.stderr.strip() or 'unknown error')
        except (json.JSONDecodeError, ValueError):
            err_msg = proc.stderr.strip() or proc.stdout.strip() or f'exit code {proc.returncode}'
        return None, f'candidate subprocess error: {err_msg}'
    
    try:
        result = json.loads(proc.stdout)
        return result, None
    except json.JSONDecodeError as exc:
        return None, f'candidate subprocess output is not valid JSON: {exc}'


def _load_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _coerce_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer, got bool")
    try:
        coerced = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if isinstance(value, numbers.Real) and not isinstance(value, numbers.Integral):
        if float(value) != float(coerced):
            raise ValueError(f"{field} must be an integer")
    return coerced


def _check_evolve_block(candidate_path, original_path):
    """Verify that code outside EVOLVE-BLOCK-START/END markers has not been modified."""
    EVOLVE_START = '# EVOLVE-BLOCK-START'
    EVOLVE_END = '# EVOLVE-BLOCK-END'
    
    for label, path in [('Original', original_path), ('Candidate', candidate_path)]:
        if not path.is_file():
            return False, label + ' file not found: ' + str(path)
    
    original_text = original_path.read_text(encoding='utf-8')
    candidate_text = candidate_path.read_text(encoding='utf-8')
    
    def _get_outer_regions(text):
        lines = text.splitlines(keepends=True)
        start_idx = None
        end_idx = None
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == EVOLVE_START:
                start_idx = i
            elif stripped == EVOLVE_END:
                end_idx = i
        
        if start_idx is None:
            return '', ''
        if end_idx is None:
            return '', ''
        
        before = ''.join(lines[:start_idx])
        after = ''.join(lines[end_idx + 1:])
        return before, after
    
    orig_before, orig_after = _get_outer_regions(original_text)
    cand_before, cand_after = _get_outer_regions(candidate_text)
    
    if orig_before != cand_before:
        return False, 'EVOLVE-BLOCK violation: code before EVOLVE-BLOCK-START was modified'
    
    if orig_after != cand_after:
        return False, 'EVOLVE-BLOCK violation: code after EVOLVE-BLOCK-END was modified'
    
    return True, ''


def _get_benchmark_dir(solver_path: Path) -> Path:
    """Walk up from the candidate path to find the FJSP-WF benchmark root."""
    for parent in [solver_path.resolve().parent] + list(solver_path.resolve().parents):
        if (parent / "data" / "benchmark_instances.json").is_file():
            return parent
        if (parent / "Task.md").is_file():
            return parent
    raise FileNotFoundError(
        "Cannot find FJSP-WF benchmark root (no data/benchmark_instances.json found)"
    )


def _load_benchmark_json(benchmark_dir: Path) -> dict[str, dict[str, Any]]:
    path = benchmark_dir / "data" / "benchmark_instances.json"
    if not path.is_file():
        raise FileNotFoundError(f"benchmark_instances.json not found at {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_instance_entry(
    name: str,
    registry: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    """Resolve an instance name or alias to a registry entry.

    Supports:
    - Exact key match
    - Alias match (via 'aliases' field)
    - Official filename without extension
    - Synthetic instance names
    """
    # Direct key match
    if name in registry:
        return name, registry[name]

    # Check aliases
    for key, entry in registry.items():
        for alias in entry.get("aliases", []):
            if alias == name:
                return key, entry

    # Try matching as a filename stem
    for key, entry in registry.items():
        file_path = entry.get("file", "")
        stem = Path(file_path).stem
        if stem == name:
            return key, entry

    return None


def _load_instance_from_file(path: Path) -> dict[str, Any]:
    """Load a benchmark instance from a file.

    Supports:
    - .fjs   : Official GECCO FJSSP-WU format (parsed)
    - .fjswf : Benchmark JSON format (direct load)
    """
    suffix = path.suffix.lower()
    if suffix == ".fjs":
        return parse_fjs_file(path)
    elif suffix == ".fjswf":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    else:
        raise ValueError(
            f"Unsupported instance file format: {suffix}. "
            f"Expected .fjs or .fjswf"
        )


def load_instances(
    benchmark_dir: Path,
    instance_filter: list[str] | None,
    max_instances: int | None,
) -> list[dict[str, Any]]:
    """Load instances by name or alias from the benchmark registry."""
    registry = _load_benchmark_json(benchmark_dir)
    base_dir = benchmark_dir / "data"

    selected: list[dict[str, Any]] = []

    if instance_filter:
        # Load specific instances by name/alias
        for name in instance_filter:
            resolved = _resolve_instance_entry(name, registry)
            if resolved is None:
                print(f"Warning: unknown instance '{name}', skipping", file=sys.stderr)
                continue
            key, entry = resolved
            instance = _load_instance_from_file(base_dir / entry["file"])
            selected.append(instance)
    else:
        # Load all instances
        for key, entry in registry.items():
            # Skip entries with ci_only flag for non-CI runs
            if entry.get("ci_only"):
                continue
            instance = _load_instance_from_file(base_dir / entry["file"])
            selected.append(instance)

    selected.sort(key=lambda x: _natural_key(x["name"]))
    if max_instances is not None and max_instances > 0:
        selected = selected[:max_instances]
    return selected


def _natural_key(name: str) -> list[object]:
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p for p in parts]


def _select_instances(
    all_instances: list[dict[str, Any]],
    instance_names: list[str] | None,
    max_instances: int | None,
) -> list[dict[str, Any]]:
    if instance_names:
        name_set = set(instance_names)
        filtered = [ins for ins in all_instances if ins["name"] in name_set]
        return filtered[:max_instances] if max_instances else filtered
    return all_instances[:max_instances] if max_instances else all_instances


# ---------------------------------------------------------------------------
# Schedule validation
# ---------------------------------------------------------------------------

def validate_schedule(
    instance: dict[str, Any],
    result: dict[str, Any],
) -> ScheduleValidation:
    """Validate a FJSP-WF schedule for correctness.

    Checks:
    1. All operations are scheduled exactly once
    2. Job precedence constraints
    3. Machine non-overlap constraints
    4. Worker non-overlap constraints
    5. Machine-eligibility: operation on an eligible machine
    6. Worker-eligibility: worker can operate the assigned machine
    7. Processing time matches the assigned (machine, worker) combination
    """
    errors: list[str] = []

    if not isinstance(result, dict):
        return ScheduleValidation(False, 0, "output must be a dict", ["output is not a dict"])

    machine_schedules = result.get("machine_schedules")
    if not isinstance(machine_schedules, list):
        return ScheduleValidation(
            False, 0, "output must include machine_schedules as a list",
            ["machine_schedules missing or not a list"],
        )

    num_jobs = instance["num_jobs"]
    num_machines = instance["num_machines"]
    num_workers = instance["num_workers"]
    operations: list[dict[str, Any]] = instance["operations"]
    worker_eligibility: list[list[int]] = instance.get("worker_eligibility", [])

    # Worker eligibility set
    worker_machines: list[set[int]] = []
    for w in range(num_workers):
        if w < len(worker_eligibility):
            worker_machines.append(set(worker_eligibility[w]))
        else:
            worker_machines.append(set(range(num_machines)))

    op_map: dict[tuple[int, int], dict[str, Any]] = {}
    for op in operations:
        op_map[(op["job_id"], op["op_idx"])] = op

    total_operations = len(operations)

    # Check machine_schedules length
    if len(machine_schedules) != num_machines:
        errors.append(
            f"machine_schedules has {len(machine_schedules)} machines, "
            f"expected {num_machines}"
        )

    scheduled_ops: dict[tuple[int, int], dict[str, Any]] = {}
    op_starts: dict[tuple[int, int], int] = {}
    op_ends: dict[tuple[int, int], int] = {}
    op_workers: dict[tuple[int, int], int] = {}
    op_machines: dict[tuple[int, int], int] = {}

    for machine_id, machine_ops in enumerate(machine_schedules):
        if not isinstance(machine_ops, list):
            errors.append(f"machine_schedules[{machine_id}] must be a list")
            continue

        intervals: list[tuple[int, int, int, int]] = []
        for op_pos, operation in enumerate(machine_ops):
            if not isinstance(operation, dict):
                errors.append(f"machine_schedules[{machine_id}][{op_pos}] must be a dict")
                continue

            required = ["job_id", "operation_index", "machine_id", "worker_id",
                        "start_time", "end_time", "duration"]
            for field in required:
                if field not in operation:
                    errors.append(
                        f"machine_schedules[{machine_id}][{op_pos}] missing '{field}'"
                    )

            if any(field not in operation for field in ["job_id", "operation_index"]):
                continue

            try:
                job_id = _coerce_int(operation["job_id"], f"[{machine_id}][{op_pos}].job_id")
                op_idx = _coerce_int(
                    operation["operation_index"], f"[{machine_id}][{op_pos}].operation_index"
                )
                sched_machine = _coerce_int(
                    operation.get("machine_id", machine_id),
                    f"[{machine_id}][{op_pos}].machine_id",
                )
                worker_id = _coerce_int(
                    operation["worker_id"], f"[{machine_id}][{op_pos}].worker_id"
                )
                start_time = _coerce_int(
                    operation["start_time"], f"[{machine_id}][{op_pos}].start_time"
                )
                end_time = _coerce_int(
                    operation["end_time"], f"[{machine_id}][{op_pos}].end_time"
                )
                duration = _coerce_int(
                    operation["duration"], f"[{machine_id}][{op_pos}].duration"
                )
            except (ValueError, KeyError) as exc:
                errors.append(f"field error at [{machine_id}][{op_pos}]: {exc}")
                continue

            if job_id < 0 or job_id >= num_jobs:
                errors.append(
                    f"[{machine_id}][{op_pos}] references invalid job {job_id}"
                )
                continue
            if op_idx < 0 or op_idx >= len([o for o in operations if o["job_id"] == job_id]):
                errors.append(
                    f"[{machine_id}][{op_pos}] references invalid op {op_idx} for job {job_id}"
                )
                continue

            # Machine assignment consistency
            if sched_machine != machine_id:
                errors.append(
                    f"[{machine_id}][{op_pos}] claims machine_id={sched_machine} "
                    f"but is in machine_schedules[{machine_id}]"
                )

            # Machine eligibility
            op_def = op_map.get((job_id, op_idx))
            if op_def is not None:
                eligible = op_def.get("eligible_machines", [])
                if machine_id not in eligible:
                    errors.append(
                        f"op({job_id},{op_idx}) assigned to ineligible machine {machine_id} "
                        f"(eligible: {eligible})"
                    )

            # Worker eligibility
            if worker_id < 0 or worker_id >= num_workers:
                errors.append(
                    f"[{machine_id}][{op_pos}] references invalid worker {worker_id}"
                )
                continue
            if machine_id not in worker_machines[worker_id]:
                errors.append(
                    f"worker {worker_id} cannot operate machine {machine_id} "
                    f"(eligible machines: {sorted(worker_machines[worker_id])})"
                )

            # Time validity
            if start_time < 0:
                errors.append(f"[{machine_id}][{op_pos}] negative start_time {start_time}")
            if end_time < start_time:
                errors.append(
                    f"[{machine_id}][{op_pos}] end_time {end_time} < start_time {start_time}"
                )
            if duration != end_time - start_time:
                errors.append(
                    f"[{machine_id}][{op_pos}] duration {duration} != "
                    f"end - start ({end_time - start_time})"
                )
            if duration <= 0:
                errors.append(
                    f"[{machine_id}][{op_pos}] non-positive duration {duration}"
                )

            # Processing time match
            if op_def is not None:
                ptimes = op_def.get("processing_times", [])
                if machine_id in op_def.get("eligible_machines", []):
                    m_idx = op_def["eligible_machines"].index(machine_id)
                    if m_idx < len(ptimes) and worker_id < len(ptimes[m_idx]):
                        expected_duration = ptimes[m_idx][worker_id]
                        if (expected_duration <= 0 < duration) or (expected_duration > 0 and duration != expected_duration):
                            errors.append(
                                f"[{machine_id}][{op_pos}] duration {duration} != "
                                f"expected {expected_duration} for (M{machine_id}, W{worker_id})"
                            )

            # Duplicate check
            key = (job_id, op_idx)
            if key in scheduled_ops:
                errors.append(f"op({job_id},{op_idx}) scheduled more than once")
            scheduled_ops[key] = operation
            op_starts[key] = start_time
            op_ends[key] = end_time
            op_workers[key] = worker_id
            op_machines[key] = machine_id
            intervals.append((start_time, end_time, job_id, op_idx))

        # Machine non-overlap
        intervals.sort(key=lambda x: x[0])
        for i in range(1, len(intervals)):
            if intervals[i][0] < intervals[i - 1][1]:
                errors.append(
                    f"machine {machine_id}: op({intervals[i][2]},{intervals[i][3]}) "
                    f"starts at {intervals[i][0]} but previous op ends at {intervals[i - 1][1]}"
                )

    # All operations scheduled
    for op in operations:
        key = (op["job_id"], op["op_idx"])
        if key not in scheduled_ops:
            errors.append(f"op({key[0]},{key[1]}) was never scheduled")

    # Job precedence
    for job_id in range(num_jobs):
        job_ops = sorted(
            [o for o in operations if o["job_id"] == job_id],
            key=lambda x: x["op_idx"],
        )
        for i in range(1, len(job_ops)):
            prev_key = (job_id, job_ops[i - 1]["op_idx"])
            curr_key = (job_id, job_ops[i]["op_idx"])
            if prev_key in op_ends and curr_key in op_starts:
                if op_starts[curr_key] < op_ends[prev_key]:
                    errors.append(
                        f"job {job_id}: op {job_ops[i]['op_idx']} starts at "
                        f"{op_starts[curr_key]} but previous op ends at "
                        f"{op_ends[prev_key]}"
                    )

    # Worker non-overlap
    worker_intervals: dict[int, list[tuple[int, int, int, int, int]]] = {
        w: [] for w in range(num_workers)
    }
    for key, worker_id in op_workers.items():
        job_id, op_idx = key
        worker_intervals.setdefault(worker_id, []).append(
            (op_starts[key], op_ends[key], job_id, op_idx, op_machines[key])
        )
    for worker_id, intervals in worker_intervals.items():
        intervals.sort(key=lambda x: x[0])
        for i in range(1, len(intervals)):
            if intervals[i][0] < intervals[i - 1][1]:
                errors.append(
                    f"worker {worker_id}: op({intervals[i][2]},{intervals[i][3]}) "
                    f"on machine {intervals[i][4]} starts at {intervals[i][0]} "
                    f"but previous op ends at {intervals[i - 1][1]}"
                )

    actual_makespan = max(op_ends.values()) if op_ends else 0
    is_valid = len(errors) == 0
    note = None if is_valid else f"schedule violations: {errors[0]}"
    return ScheduleValidation(is_valid, actual_makespan, note, errors)


def compute_score(baseline_makespan: int | None, agent_makespan: int | None) -> float | None:
    """Relative score: baseline_makespan / agent_makespan."""
    if baseline_makespan is None or agent_makespan is None or agent_makespan <= 0:
        return None
    if baseline_makespan <= 0:
        return None
    return float(baseline_makespan) / float(agent_makespan)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_instances(
    instances: list[dict[str, Any]],
    baseline_mod: ModuleType,
    candidate_path: Path,
) -> list[InstanceResult]:
    results: list[InstanceResult] = []

    for instance in instances:
        name = instance["name"]
        num_jobs = instance["num_jobs"]
        num_machines = instance["num_machines"]
        num_workers = instance["num_workers"]
        operations = instance["operations"]
        total_ops = len(operations)

        # Run baseline
        t0 = time.perf_counter()
        try:
            baseline_result = baseline_mod.solve_instance(instance)
            baseline_elapsed = time.perf_counter() - t0
            baseline_val = validate_schedule(instance, baseline_result)
            baseline_makespan = baseline_val.actual_makespan if baseline_val.valid else None
            baseline_valid = baseline_val.valid
            baseline_note = baseline_val.note
        except Exception as exc:
            baseline_elapsed = time.perf_counter() - t0
            baseline_makespan = None
            baseline_valid = False
            baseline_note = f"baseline exception: {exc}"

        # Run agent solver (subprocess)
        t0 = time.perf_counter()
        agent_result, agent_err = _run_candidate_subprocess(candidate_path, instance)
        agent_elapsed = time.perf_counter() - t0
        if agent_err:
            agent_makespan = None
            agent_valid = False
            agent_note = agent_err
        else:
            agent_val = validate_schedule(instance, agent_result)
            agent_makespan = agent_val.actual_makespan if agent_val.valid else None
            agent_valid = agent_val.valid
            agent_note = agent_val.note

        score = compute_score(baseline_makespan, agent_makespan)

        results.append(InstanceResult(
            name=name,
            num_jobs=num_jobs,
            num_machines=num_machines,
            num_workers=num_workers,
            total_operations=total_ops,
            baseline_makespan=baseline_makespan,
            baseline_valid=baseline_valid,
            baseline_note=baseline_note,
            baseline_elapsed_s=baseline_elapsed,
            agent_makespan=agent_makespan,
            agent_valid=agent_valid,
            agent_note=agent_note,
            agent_elapsed_s=agent_elapsed,
            score=score,
        ))

    return results


def print_report(results: list[InstanceResult]) -> None:
    print(f"{'Instance':30} | {'Valid':6} | {'Baseline':9} | {'Agent':9} | {'Score':7} | "
          f"B.Elap | A.Elap")
    print("-" * 85)
    for row in results:
        b_status = "ok" if row.baseline_valid else "FAIL"
        a_status = "ok" if row.agent_valid else "FAIL"
        b_str = str(row.baseline_makespan) if row.baseline_makespan is not None else "N/A"
        a_str = str(row.agent_makespan) if row.agent_makespan is not None else "N/A"
        s_str = f"{row.score:.4f}" if row.score is not None else " N/A "
        print(
            f"{row.name:30} | {a_status:6} | {b_str:>9} | {a_str:>9} | {s_str:>7} | "
            f"{row.baseline_elapsed_s:.3f}s | {row.agent_elapsed_s:.3f}s"
        )

    scores = [r.score for r in results if r.score is not None]
    valid_count = sum(1 for r in results if r.agent_valid)
    total = len(results)

    print(f"\nSummary [{FAMILY}]")
    print(f"- instances: {total}")
    print(f"- valid schedules: {valid_count}/{total}")
    if scores:
        print(f"- avg relative score (baseline/agent): {statistics.fmean(scores):.4f}")
        print(f"- min score: {min(scores):.4f}")
        print(f"- max score: {max(scores):.4f}")
    else:
        print("- avg relative score: N/A (no valid results)")

    issues = [r for r in results if r.agent_note is not None or r.baseline_note is not None]
    if issues:
        print("\nNotes:")
        for row in issues[:5]:
            if row.agent_note:
                print(f"- {row.name} (agent): {row.agent_note}")
            if row.baseline_note:
                print(f"- {row.name} (baseline): {row.baseline_note}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Evaluate FJSP-WF scheduling solutions."
    )
    parser.add_argument("candidate", type=str,
                        help="Path to the candidate solver (e.g., scripts/init.py)")
    parser.add_argument("--instances", nargs="*", default=None,
                        help="Instance names or aliases (e.g., mk01, brandimarte_mk07)")
    parser.add_argument("--max-instances", type=int, default=None,
                        help="Evaluate only the first N instances.")
    parser.add_argument("--metrics-out", type=str, default=None,
                        help="Path for metrics.json output.")
    parser.add_argument("--artifacts-out", type=str, default=None,
                        help="Path for artifacts.json output.")
    args = parser.parse_args()

    candidate_path = Path(args.candidate).resolve()
    if not candidate_path.is_file():
        print(f"Error: candidate file not found: {candidate_path}", file=sys.stderr)
        return 1

    benchmark_dir = _get_benchmark_dir(candidate_path)
    baseline_path = benchmark_dir / "baseline" / "solution.py"
    if not baseline_path.is_file():
        print(f"Error: baseline not found at {baseline_path}", file=sys.stderr)
        return 1

    # EVOLVE-BLOCK validation
    original_solver_path = benchmark_dir / "scripts" / "init.py"
    evolve_ok, evolve_msg = _check_evolve_block(candidate_path, original_solver_path)
    if not evolve_ok:
        print(f"Error: {evolve_msg}", file=sys.stderr)
        return 1
    
    # Load baseline module (candidate runs in subprocess)
    try:
        baseline_mod = _load_module("fjspwf_baseline", baseline_path)
    except Exception as exc:
        print(f"Error loading baseline module: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    # Load instances
    all_instances = load_instances(benchmark_dir, args.instances, args.max_instances)
    if not all_instances:
        print("Error: no instances found to evaluate", file=sys.stderr)
        return 1

    # Evaluate
    t0 = time.perf_counter()
    results = evaluate_instances(all_instances, baseline_mod, candidate_path)
    wall_time = time.perf_counter() - t0

    # Print report
    print_report(results)

    # Compute aggregate metrics
    scores = [r.score for r in results if r.score is not None]
    combined_score = statistics.fmean(scores) if scores else 0.0
    valid = 1.0 if all(r.agent_valid for r in results) else 0.0
    baseline_failures = sum(1 for r in results if not r.baseline_valid)
    agent_failures = sum(1 for r in results if not r.agent_valid)

    metrics = {
        "combined_score": combined_score,
        "valid": valid,
        "instances": float(len(results)),
        "baseline_failures": float(baseline_failures),
        "agent_failures": float(agent_failures),
        "baseline_success_rate": float(len(results) - baseline_failures) / float(len(results)) if results else 0.0,
        "agent_success_rate": float(len(results) - agent_failures) / float(len(results)) if results else 0.0,
        "avg_score": combined_score,
        "evaluation_wall_time_s": wall_time,
    }

    # Write outputs
    metrics_out = Path(args.metrics_out) if args.metrics_out else (benchmark_dir / "metrics.json")
    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    metrics_out.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nMetrics written to {metrics_out}")

    if args.artifacts_out:
        artifacts = {
            "family": FAMILY,
            "candidate_path": str(candidate_path),
            "baseline_path": str(baseline_path),
            "instances": [r.name for r in results],
            "evaluation_wall_time_s": wall_time,
            "combined_score": combined_score,
        }
        artifacts_path = Path(args.artifacts_out)
        artifacts_path.parent.mkdir(parents=True, exist_ok=True)
        artifacts_path.write_text(
            json.dumps(artifacts, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

