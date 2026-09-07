"""Evaluate a candidate solver and the reference solver on ORB (Applegate & Cook, 1991).

The candidate (`baseline/init.py`) is untrusted, so:

- it runs in its own subprocess and hands back only a schedule -- never a
  module, never a score;
- it receives an instance projected down to `name` / `duration_matrix` /
  `machines_matrix`. `metadata` (optimum, lower/upper bound) is the scoring
  denominator and the answer key, and is never handed to the thing being scored;
- benchmark instances are loaded here from the vendored
  `JobShop/data/benchmark_instances.json`, never from the candidate.

Reference uses `job_shop_lib` + OR-Tools and is reported for comparison only; it
never contributes to the candidate's score.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import numbers
import os
import re
import shutil
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


FAMILY_PREFIX = "orb"
FAMILY_NAME = "ORB (Applegate & Cook, 1991)"


# --------------------------------------------------------------------------
# Trusted evaluation data and candidate isolation.
#
# Everything in this file is scorer-owned. The candidate never supplies
# instance data, never sees `metadata` (optimum / bounds / reference), and
# never runs inside this process: it is executed in a subprocess that gets a
# projected instance and hands back nothing but a schedule.
# --------------------------------------------------------------------------

#: The only instance fields a candidate is allowed to see. `metadata` (which
#: carries `optimum`, `lower_bound`, `upper_bound`) is deliberately absent: it
#: is both the scoring denominator and a free answer key.
PUBLIC_INSTANCE_FIELDS = ("name", "duration_matrix", "machines_matrix")

#: Environment handed to the candidate subprocess. Kept narrow so the candidate
#: cannot follow FRONTIER_ENGINEERING_ROOT (or any other harness variable) back
#: to the benchmark JSON it is not supposed to read.
CANDIDATE_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TMP",
    "TEMP",
    "PYTHONHASHSEED",
    "SYSTEMROOT",
)

DEFAULT_CANDIDATE_TIMEOUT_S = 120.0

_BENCHMARK_JSON_RELPATH = ("benchmarks", "JobShop", "data", "benchmark_instances.json")


def _import_candidate_sandbox() -> ModuleType:
    """Import the shared isolation helper, before any candidate code runs.

    `benchmarks/_shared/` sits outside every benchmark directory, so a task's
    `copy_files.txt` of `.` cannot drag it into the sandbox where a candidate
    could rewrite it.
    """
    try:  # already on sys.path (evaluate_unified.py puts it there)
        import candidate_sandbox  # type: ignore

        return candidate_sandbox
    except ImportError:
        pass

    roots: list[Path] = []
    env_root = str(os.environ.get("FRONTIER_ENGINEERING_ROOT", "")).strip()
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())
    roots.extend(Path(__file__).resolve().parents)

    for root in roots:
        shared = root / "benchmarks" / "_shared"
        if (shared / "candidate_sandbox.py").is_file():
            sys.path.insert(0, str(shared))
            import candidate_sandbox  # type: ignore

            return candidate_sandbox

    raise RuntimeError(
        "benchmarks/_shared/candidate_sandbox.py not found; set "
        "FRONTIER_ENGINEERING_ROOT to the repository root."
    )


sandbox = _import_candidate_sandbox()


#: Scorer-owned program executed in the candidate's subprocess. It loads the
#: candidate module by path, calls `solve_instance(instance)` once, and writes
#: the schedule to submission.json. Living here (in a readonly, fingerprinted
#: file) rather than on disk in the task tree means the candidate cannot swap
#: it out.
CANDIDATE_RUNNER_SOURCE = '''"""Isolated runner: ask the candidate for one schedule, return only data."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: runner.py <candidate.py> <instance.json> <submission.json>", file=sys.stderr)
        return 2

    candidate_path = Path(sys.argv[1]).resolve()
    instance_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])

    instance = json.loads(instance_path.read_text(encoding="utf-8"))

    spec = importlib.util.spec_from_file_location("jobshop_candidate", candidate_path)
    if spec is None or spec.loader is None:
        print(f"cannot import candidate module from {candidate_path}", file=sys.stderr)
        return 3
    module = importlib.util.module_from_spec(spec)
    sys.modules["jobshop_candidate"] = module
    spec.loader.exec_module(module)

    solve_instance = getattr(module, "solve_instance", None)
    if not callable(solve_instance):
        print("candidate must define solve_instance(instance) -> dict", file=sys.stderr)
        return 4

    result = solve_instance(instance)
    if not isinstance(result, dict):
        print("solve_instance must return a dict", file=sys.stderr)
        return 5

    # Only the schedule crosses the process boundary. A reported makespan is
    # carried over for cross-checking; the scorer recomputes its own.
    payload = {"machine_schedules": result.get("machine_schedules")}
    if result.get("makespan") is not None:
        payload["makespan"] = result["makespan"]

    output_path.write_text(json.dumps(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _natural_key(name: str) -> list[object]:
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p for p in parts]


def _benchmark_json_path(explicit: Path | str | None = None) -> Path:
    """Locate the vendored benchmark JSON. Scorer-side only, never candidate-side."""
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"benchmark JSON not found: {path}")
        return path

    candidates: list[Path] = []
    env_root = str(os.environ.get("FRONTIER_ENGINEERING_ROOT", "")).strip()
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve().joinpath(*_BENCHMARK_JSON_RELPATH))
    # <repo>/benchmarks/JobShop/<family>/verification/evaluate.py
    candidates.append(Path(__file__).resolve().parents[2] / "data" / "benchmark_instances.json")
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent.joinpath(*_BENCHMARK_JSON_RELPATH))

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        "benchmark_instances.json not found. Set FRONTIER_ENGINEERING_ROOT to the "
        "repository root, or pass an explicit path."
    )


def load_benchmark_json(json_path: Path | str | None = None) -> dict[str, dict]:
    with _benchmark_json_path(json_path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("benchmark_instances.json must contain a JSON object")
    return data


def load_family_instances(json_path: Path | str | None = None) -> list[dict]:
    """Return this family's instances, with full metadata, from trusted data."""
    data = load_benchmark_json(json_path)
    selected = [value for name, value in data.items() if name.startswith(FAMILY_PREFIX)]
    if not selected:
        raise ValueError(f"no instances found for family prefix {FAMILY_PREFIX!r}")
    return sorted(selected, key=lambda item: _natural_key(item["name"]))


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _default_candidate_timeout_s() -> float:
    raw = str(os.environ.get("JOBSHOP_CANDIDATE_TIMEOUT_S", "")).strip()
    if not raw:
        return DEFAULT_CANDIDATE_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_CANDIDATE_TIMEOUT_S
    return value if value > 0 else DEFAULT_CANDIDATE_TIMEOUT_S


def public_instance_view(instance: dict, *, anonymize_name: bool = False) -> dict:
    """Project a trusted instance down to what the candidate is allowed to see."""
    missing = [field for field in PUBLIC_INSTANCE_FIELDS if field not in instance]
    if missing:
        raise ValueError(f"instance is missing required field(s): {missing}")
    view = {field: instance[field] for field in PUBLIC_INSTANCE_FIELDS}
    if anonymize_name:
        digest = hashlib.sha256(str(instance["name"]).encode("utf-8")).hexdigest()[:12]
        view["name"] = f"instance_{digest}"
    return view


def run_candidate_on_instance(
    runner_path: Path,
    candidate_path: Path,
    instance: dict,
    *,
    timeout_s: float,
    anonymize_name: bool = False,
) -> tuple[dict | None, str | None]:
    """Run the candidate on one instance in its own process.

    Returns `(submission, error)`; exactly one of the two is None. The
    submission is unvalidated data -- feasibility and makespan are decided by
    `_validate_baseline_schedule` against the trusted instance.
    """
    payload = json.dumps(
        public_instance_view(instance, anonymize_name=anonymize_name)
    ).encode("utf-8")

    try:
        run = sandbox.run_candidate_isolated(
            runner_path,
            inputs={"instance.json": payload},
            expected_outputs=("submission.json",),
            timeout_s=timeout_s,
            argv=[str(Path(candidate_path).resolve()), "instance.json", "submission.json"],
            copy_into_workdir=True,
            env_allowlist=CANDIDATE_ENV_ALLOWLIST,
        )
    except sandbox.InvalidSubmissionError as exc:
        return None, str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"failed to run candidate: {exc}"

    if run.timed_out:
        return None, f"candidate timed out after {timeout_s:g}s"
    if run.returncode != 0:
        detail = (run.stderr_tail or run.stdout_tail or "").strip().splitlines()
        tail = detail[-1] if detail else "no output"
        return None, f"candidate exited non-zero ({run.returncode}): {tail[:400]}"

    try:
        submission = sandbox.load_json_output(run)
    except sandbox.InvalidSubmissionError as exc:
        return None, str(exc)
    return submission, None


@dataclass
class InstanceResult:
    name: str
    optimum: int | None
    lower_bound: int | None
    upper_bound: int | None
    baseline_makespan: int | None
    baseline_valid: bool
    baseline_note: str | None
    baseline_elapsed_s: float
    reference_makespan: int | None
    reference_elapsed_s: float | None
    reference_error: str | None


@dataclass
class ScheduleValidation:
    actual_makespan: int
    note: str | None


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
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if isinstance(value, numbers.Real) and not isinstance(value, numbers.Integral):
        if float(value) != float(coerced):
            raise ValueError(f"{field} must be an integer")
    return coerced


def _validate_baseline_schedule(
    instance: dict,
    result: object,
) -> ScheduleValidation:
    if not isinstance(result, dict):
        raise ValueError("solver output must be a dict")

    machine_schedules = result.get("machine_schedules")
    if not isinstance(machine_schedules, list):
        raise ValueError("solver output must include machine_schedules as a list")

    durations: list[list[int]] = instance["duration_matrix"]
    machines: list[list[int]] = instance["machines_matrix"]
    num_jobs = len(durations)
    num_machines = (
        max((machine_id for row in machines for machine_id in row), default=-1) + 1
    )
    expected_operation_count = sum(len(job) for job in durations)

    if len(machine_schedules) != num_machines:
        raise ValueError(
            f"machine_schedules has {len(machine_schedules)} machines, "
            f"expected {num_machines}"
        )

    seen_operations: set[tuple[int, int]] = set()
    operation_starts: dict[tuple[int, int], int] = {}
    operation_ends: dict[tuple[int, int], int] = {}
    actual_makespan = 0

    for machine_id, machine_ops in enumerate(machine_schedules):
        if not isinstance(machine_ops, list):
            raise ValueError(f"machine_schedules[{machine_id}] must be a list")

        intervals: list[tuple[int, int, int, int]] = []
        for op_pos, operation in enumerate(machine_ops):
            if not isinstance(operation, dict):
                raise ValueError(
                    f"machine_schedules[{machine_id}][{op_pos}] must be a dict"
                )
            for field in ("job_id", "operation_index", "start_time", "end_time"):
                if field not in operation:
                    raise ValueError(
                        f"machine_schedules[{machine_id}][{op_pos}] is missing {field}"
                    )

            job_id = _coerce_int(
                operation["job_id"],
                f"machine_schedules[{machine_id}][{op_pos}].job_id",
            )
            op_idx = _coerce_int(
                operation["operation_index"],
                f"machine_schedules[{machine_id}][{op_pos}].operation_index",
            )
            start_time = _coerce_int(
                operation["start_time"],
                f"machine_schedules[{machine_id}][{op_pos}].start_time",
            )
            end_time = _coerce_int(
                operation["end_time"],
                f"machine_schedules[{machine_id}][{op_pos}].end_time",
            )

            if job_id < 0 or job_id >= num_jobs:
                raise ValueError(
                    f"machine_schedules[{machine_id}][{op_pos}] references "
                    f"unknown job {job_id}"
                )
            if op_idx < 0 or op_idx >= len(durations[job_id]):
                raise ValueError(
                    f"machine_schedules[{machine_id}][{op_pos}] references "
                    f"unknown operation {op_idx} for job {job_id}"
                )
            if start_time < 0:
                raise ValueError(
                    f"job {job_id} op {op_idx} has negative start_time {start_time}"
                )
            if end_time < start_time:
                raise ValueError(
                    f"job {job_id} op {op_idx} ends before it starts"
                )

            expected_machine = machines[job_id][op_idx]
            if expected_machine != machine_id:
                raise ValueError(
                    f"job {job_id} op {op_idx} scheduled on machine {machine_id}, "
                    f"expected machine {expected_machine}"
                )

            expected_duration = durations[job_id][op_idx]
            actual_duration = end_time - start_time
            if actual_duration != expected_duration:
                raise ValueError(
                    f"job {job_id} op {op_idx} duration {actual_duration} does not "
                    f"match expected {expected_duration}"
                )

            if "duration" in operation and operation["duration"] is not None:
                duration = _coerce_int(
                    operation["duration"],
                    f"machine_schedules[{machine_id}][{op_pos}].duration",
                )
                if duration != expected_duration:
                    raise ValueError(
                        f"job {job_id} op {op_idx} reported duration {duration} "
                        f"does not match expected {expected_duration}"
                    )

            op_key = (job_id, op_idx)
            if op_key in seen_operations:
                raise ValueError(
                    f"job {job_id} op {op_idx} appears more than once in the schedule"
                )

            seen_operations.add(op_key)
            operation_starts[op_key] = start_time
            operation_ends[op_key] = end_time
            intervals.append((start_time, end_time, job_id, op_idx))
            actual_makespan = max(actual_makespan, end_time)

        prev_end: int | None = None
        prev_op: tuple[int, int] | None = None
        for start_time, end_time, job_id, op_idx in sorted(intervals):
            if prev_end is not None and start_time < prev_end and prev_op is not None:
                raise ValueError(
                    f"machine {machine_id} overlaps job {prev_op[0]} op {prev_op[1]} "
                    f"with job {job_id} op {op_idx}"
                )
            prev_end = end_time
            prev_op = (job_id, op_idx)

    if len(seen_operations) != expected_operation_count:
        missing = [
            f"job {job_id} op {op_idx}"
            for job_id, job in enumerate(durations)
            for op_idx in range(len(job))
            if (job_id, op_idx) not in seen_operations
        ]
        missing_preview = ", ".join(missing[:5])
        if len(missing) > 5:
            missing_preview += ", ..."
        raise ValueError(
            f"schedule is missing {len(missing)} operations: {missing_preview}"
        )

    for job_id, job in enumerate(durations):
        for op_idx in range(len(job) - 1):
            current_op = (job_id, op_idx)
            next_op = (job_id, op_idx + 1)
            if operation_starts[next_op] < operation_ends[current_op]:
                raise ValueError(
                    f"job {job_id} violates precedence between op {op_idx} "
                    f"and op {op_idx + 1}"
                )

    # A self-reported makespan is optional under the schedule-only contract and
    # is never scored: `actual_makespan`, recomputed above from the trusted
    # instance, is what the caller uses. When the candidate does report one it
    # still has to agree, so a bogus self-report is a rejection rather than a
    # free pass.
    reported = result.get("makespan")
    if reported is not None:
        reported_makespan = _coerce_int(reported, "makespan")
        if reported_makespan != actual_makespan:
            raise ValueError(
                f"reported makespan {reported_makespan} does not match recomputed "
                f"{actual_makespan}"
            )

    return ScheduleValidation(actual_makespan=actual_makespan, note=None)


def _score(target: int | None, makespan: int | None) -> float | None:
    if target is None or makespan is None or makespan <= 0:
        return None
    return min(100.0, 100.0 * float(target) / float(makespan))


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.fmean(values)


def _fmt_int(value: int | None) -> str:
    return "-" if value is None else str(value)


def _fmt_float(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _select_instances(
    all_instances: list[dict],
    names: list[str] | None,
    max_instances: int | None,
) -> list[dict]:
    selected = all_instances
    if names:
        by_name = {ins["name"]: ins for ins in selected}
        missing = [name for name in names if name not in by_name]
        if missing:
            raise ValueError(
                f"Unknown instance(s): {missing}. "
                f"Known prefix={FAMILY_PREFIX}."
            )
        selected = [by_name[name] for name in names]
    if max_instances is not None:
        selected = selected[: max(max_instances, 0)]
    return selected


def evaluate_instances(
    instances: list[dict],
    reference_time_limit: float,
    candidate_path: Path | str,
    reference_mod: ModuleType | None = None,
    *,
    candidate_timeout_s: float | None = None,
    anonymize_names: bool | None = None,
) -> list[InstanceResult]:
    """Score a candidate against trusted instances.

    `instances` must come from `load_family_instances()` (or an equivalent
    trusted source): they carry the metadata used as the scoring denominator and
    the matrices used for feasibility checking. The candidate only ever receives
    the projection produced by `public_instance_view`.
    """
    candidate_path = Path(candidate_path).resolve()
    if not candidate_path.is_file():
        raise FileNotFoundError(f"candidate not found: {candidate_path}")

    if candidate_timeout_s is None:
        candidate_timeout_s = _default_candidate_timeout_s()
    if anonymize_names is None:
        anonymize_names = _env_flag("JOBSHOP_ANONYMIZE_INSTANCE_NAMES")

    reference_map: dict = {}
    reference_setup_error: str | None = None
    if reference_mod is None:
        reference_setup_error = "reference solver unavailable"
    else:
        try:
            reference_map = {ins.name: ins for ins in reference_mod.load_family_instances()}
        except Exception as exc:  # pragma: no cover - environment dependent
            reference_setup_error = f"failed to load reference instances: {exc}"

    results: list[InstanceResult] = []
    runner_dir = Path(tempfile.mkdtemp(prefix="jobshop_runner_"))
    try:
        runner_path = runner_dir / "candidate_runner.py"
        runner_path.write_text(CANDIDATE_RUNNER_SOURCE, encoding="utf-8")

        for instance in instances:
            meta = instance.get("metadata") or {}
            optimum = meta.get("optimum")
            lower_bound = meta.get("lower_bound")
            upper_bound = meta.get("upper_bound")

            baseline_makespan: int | None = None
            baseline_valid = False
            baseline_note: str | None = None

            start = time.perf_counter()
            submission, run_error = run_candidate_on_instance(
                runner_path,
                candidate_path,
                instance,
                timeout_s=float(candidate_timeout_s),
                anonymize_name=bool(anonymize_names),
            )
            baseline_elapsed = time.perf_counter() - start

            if submission is None:
                baseline_note = run_error
            else:
                try:
                    validation = _validate_baseline_schedule(instance, submission)
                    baseline_makespan = validation.actual_makespan
                    baseline_valid = True
                    baseline_note = validation.note
                except Exception as exc:
                    baseline_note = str(exc)

            reference_makespan: int | None = None
            reference_elapsed: float | None = None
            reference_error: str | None = reference_setup_error

            if reference_setup_error is None:
                try:
                    ref_instance = reference_map[instance["name"]]
                    start = time.perf_counter()
                    ref_schedule = reference_mod.solve_instance(
                        ref_instance,
                        max_time_in_seconds=reference_time_limit,
                    )
                    reference_elapsed = time.perf_counter() - start
                    reference_makespan = ref_schedule.makespan()
                except Exception as exc:  # pragma: no cover - environment dependent
                    reference_error = str(exc)

            results.append(
                InstanceResult(
                    name=instance["name"],
                    optimum=optimum,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                    baseline_makespan=baseline_makespan,
                    baseline_valid=baseline_valid,
                    baseline_note=baseline_note,
                    baseline_elapsed_s=baseline_elapsed,
                    reference_makespan=reference_makespan,
                    reference_elapsed_s=reference_elapsed,
                    reference_error=reference_error,
                )
            )
    finally:
        shutil.rmtree(runner_dir, ignore_errors=True)

    return results


def print_report(results: list[InstanceResult]) -> None:
    if not results:
        print("No instances selected.")
        return

    print(f"Family: {FAMILY_NAME} ({FAMILY_PREFIX})")
    print(
        "Columns: instance | baseline_ok | baseline_ms | reference_ms | optimum | "
        "lower_bound | best_score(b/r) | lb_score(b/r)"
    )

    baseline_best_scores: list[float] = []
    reference_best_scores: list[float] = []
    baseline_lb_scores: list[float] = []
    reference_lb_scores: list[float] = []
    baseline_opt_gaps: list[float] = []
    reference_opt_gaps: list[float] = []

    for row in results:
        target = row.optimum if row.optimum is not None else row.upper_bound

        b_best = _score(target, row.baseline_makespan)
        r_best = _score(target, row.reference_makespan)
        b_lb = _score(row.lower_bound, row.baseline_makespan)
        r_lb = _score(row.lower_bound, row.reference_makespan)

        if b_best is not None:
            baseline_best_scores.append(b_best)
        if r_best is not None:
            reference_best_scores.append(r_best)
        if b_lb is not None:
            baseline_lb_scores.append(b_lb)
        if r_lb is not None:
            reference_lb_scores.append(r_lb)

        if row.optimum is not None and row.baseline_makespan is not None:
            baseline_opt_gaps.append(
                100.0 * (row.baseline_makespan - row.optimum) / row.optimum
            )
        if row.optimum is not None:
            if row.reference_makespan is not None:
                reference_opt_gaps.append(
                    100.0 * (row.reference_makespan - row.optimum) / row.optimum
                )

        print(
            f"{row.name:8} | "
            f"{('valid' if row.baseline_valid else 'invalid'):11} | "
            f"{_fmt_int(row.baseline_makespan):11} | "
            f"{_fmt_int(row.reference_makespan):11} | "
            f"{_fmt_int(row.optimum):7} | "
            f"{_fmt_int(row.lower_bound):11} | "
            f"{_fmt_float(b_best):>6}/{_fmt_float(r_best):<6} | "
            f"{_fmt_float(b_lb):>6}/{_fmt_float(r_lb):<6}"
        )

    baseline_diagnostics = [r for r in results if r.baseline_note is not None]
    baseline_invalid = [r for r in results if not r.baseline_valid]
    reference_failures = [r for r in results if r.reference_error is not None]

    print("\nSummary")
    print(f"- instances: {len(results)}")
    print(f"- invalid baseline schedules: {len(baseline_invalid)}")
    print(f"- reference failures: {len(reference_failures)}")
    print(
        f"- avg baseline runtime (s): "
        f"{_fmt_float(_mean([r.baseline_elapsed_s for r in results]), 4)}"
    )
    print(
        f"- avg reference runtime (s): "
        f"{_fmt_float(_mean([r.reference_elapsed_s for r in results if r.reference_elapsed_s is not None]), 4)}"
    )
    print(
        f"- avg best-known score   (baseline/reference): "
        f"{_fmt_float(_mean(baseline_best_scores))} / "
        f"{_fmt_float(_mean(reference_best_scores))}"
    )
    print(
        f"- avg lower-bound score  (baseline/reference): "
        f"{_fmt_float(_mean(baseline_lb_scores))} / "
        f"{_fmt_float(_mean(reference_lb_scores))}"
    )
    print(
        f"- avg optimality gap %   (baseline/reference, known optimum only): "
        f"{_fmt_float(_mean(baseline_opt_gaps))} / "
        f"{_fmt_float(_mean(reference_opt_gaps))}"
    )
    print("- theoretical score ceiling under score_lb formula: 100.00")

    if baseline_diagnostics:
        print("\nBaseline validation notes:")
        for row in baseline_diagnostics[:5]:
            print(f"- {row.name}: {row.baseline_note}")
        if len(baseline_diagnostics) > 5:
            print(f"- ... {len(baseline_diagnostics) - 5} more")

    if reference_failures:
        print("\nReference solver errors:")
        for err in reference_failures[:5]:
            print(f"- {err.name}: {err.reference_error}")


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description=(
            f"Evaluate a candidate solver and the reference implementation for "
            f"{FAMILY_NAME} ({FAMILY_PREFIX})."
        )
    )
    parser.add_argument(
        "--instances",
        nargs="*",
        default=None,
        help="Optional explicit instance names.",
    )
    parser.add_argument(
        "--max-instances",
        type=int,
        default=None,
        help="Evaluate only the first N selected instances.",
    )
    parser.add_argument(
        "--reference-time-limit",
        type=float,
        default=10.0,
        help="Time limit in seconds per instance for reference solver.",
    )
    parser.add_argument(
        "--candidate",
        default="",
        help="Candidate solver file (default: baseline/init.py in this family).",
    )
    parser.add_argument(
        "--candidate-timeout-s",
        type=float,
        default=None,
        help="Wall-clock limit for the candidate subprocess, per instance.",
    )
    parser.add_argument(
        "--benchmark-json",
        default="",
        help="Override the trusted benchmark_instances.json path.",
    )
    parser.add_argument(
        "--no-reference",
        action="store_true",
        help="Skip the reference solver (useful without job_shop_lib/OR-Tools).",
    )
    args = parser.parse_args()

    family_dir = Path(__file__).resolve().parents[1]
    candidate_path = (
        Path(args.candidate).resolve() if args.candidate else family_dir / "baseline" / "init.py"
    )

    reference_mod: ModuleType | None = None
    if not args.no_reference:
        try:
            reference_mod = _load_module(
                f"reference_{FAMILY_PREFIX}",
                family_dir / "verification" / "reference.py",
            )
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"warning: reference solver unavailable ({exc})", file=sys.stderr)

    all_instances = load_family_instances(args.benchmark_json or None)
    selected = _select_instances(all_instances, args.instances, args.max_instances)
    results = evaluate_instances(
        selected,
        args.reference_time_limit,
        candidate_path,
        reference_mod,
        candidate_timeout_s=args.candidate_timeout_s,
    )
    print_report(results)


if __name__ == "__main__":
    _cli()
