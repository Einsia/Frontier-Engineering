from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import os
import statistics
import sys
import time
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from verification.process_runner import BoundedResult, run_bounded  # noqa: E402

SEEDS = [210001, 210013, 210031, 210049, 210067, 210089, 210103, 210113, 210131, 210151]
SMOKE_SEED = 4161752734
INSTANCES_PER_SEED = 1
INPUT_SCHEMA = json.loads(
    "{\"additionalProperties\": false, \"propert"
    "ies\": {\"epsilon_total\": {\"minimum\": 0, \""
    "type\": \"number\"}, \"fairness\": {\"addition"
    "alProperties\": false, \"properties\": {\"ma"
    "x_group_error_ratio\": {\"minimum\": 1, \"ty"
    "pe\": \"number\"}}, \"required\": [\"max_group"
    "_error_ratio\"], \"type\": \"object\"}, \"quer"
    "ies\": {\"items\": {\"additionalProperties\":"
    " false, \"properties\": {\"business_value\":"
    " {\"minimum\": 0, \"type\": \"number\"}, \"epsi"
    "lon_max\": {\"minimum\": 0, \"type\": \"number"
    "\"}, \"epsilon_min\": {\"minimum\": 0, \"type\""
    ": \"number\"}, \"group\": {\"type\": \"string\"}"
    ", \"id\": {\"type\": \"string\"}, \"max_error\":"
    " {\"minimum\": 0, \"type\": \"number\"}, \"popu"
    "lation_coverage\": {\"minimum\": 0, \"type\":"
    " \"number\"}, \"sensitivity\": {\"minimum\": 0"
    ", \"type\": \"number\"}}, \"required\": [\"id\","
    " \"sensitivity\", \"business_value\", \"popul"
    "ation_coverage\", \"epsilon_min\", \"epsilon"
    "_max\", \"max_error\", \"group\"], \"type\": \"o"
    "bject\"}, \"type\": \"array\"}}, \"required\": "
    "[\"queries\", \"epsilon_total\", \"fairness\"]"
    ", \"type\": \"object\"}"
)
OUTPUT_SCHEMA = json.loads(
    "{\"additionalProperties\": false, \"propert"
    "ies\": {\"allocations\": {\"additionalProper"
    "ties\": true, \"type\": \"object\"}}, \"requir"
    "ed\": [\"allocations\"], \"type\": \"object\"}"
)
DIRECTION = "maximize"
AGGREGATION = "mean"
INVALID_SCORE = -1e+18
TIMEOUT_S = 10.0
MAX_OUTPUT_BYTES = 1048576
RUNTIME_IMAGE = (
    "python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b87"
    "31f1499a57e22e6c285135ae657bf7"
)
MEMORY_MB = 512
CPUS = 1.0
PIDS_LIMIT = 128


def _load_module(relative_module: str) -> ModuleType:
    path = ROOT / (relative_module.replace(".", "/") + ".py")
    module_spec = importlib.util.spec_from_file_location("benchgen_task_module", path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"cannot load task module: {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _valid(
    problem: ModuleType, instance: dict[str, Any], solution: dict[str, Any]
) -> tuple[bool, str]:
    result = problem.validate_solution(instance, solution)
    if result is None:
        return True, ""
    if isinstance(result, bool):
        return result, "" if result else "solution rejected by verifier"
    if isinstance(result, tuple) and len(result) == 2:
        return bool(result[0]), str(result[1])
    if hasattr(result, "valid"):
        return bool(result.valid), str(getattr(result, "reason", ""))
    raise TypeError("invalid validate_solution return value")


def _finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite(key) and _finite(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_finite(item) for item in value)
    return True


def _validate_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate the dependency-free JSON Schema subset supported by benchgen v1."""

    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, expected_type):
        return [f"{path}: expected {expected_type}, got {type(value).__name__}"]
    if "enum" in schema and not any(_json_equal(value, item) for item in schema["enum"]):
        errors.append(f"{path}: value is not in enum")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")
        for key, item in value.items():
            if key in properties:
                errors.extend(_validate_json_schema(item, properties[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected property {key!r}")
    elif isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than maxItems")
        if schema.get("uniqueItems"):
            canonical = [_json_key(item) for item in value]
            if len(canonical) != len(set(canonical)):
                errors.append(f"{path}: items are not unique")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                errors.extend(_validate_json_schema(item, schema["items"], f"{path}[{index}]"))
    elif isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum")
    return errors


def _json_equal(left: Any, right: Any) -> bool:
    return _json_key(left) == _json_key(right)


def _json_key(value: Any) -> Any:
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, float)):
        return ("number", value)
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, list):
        return ("array", tuple(_json_key(item) for item in value))
    if isinstance(value, dict):
        return (
            "object",
            tuple(sorted((str(key), _json_key(item)) for key, item in value.items())),
        )
    return (type(value).__name__, repr(value))


def _matches_type(value: Any, expected: str | list[str]) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    checks = {
        "null": lambda item: item is None,
        "boolean": lambda item: isinstance(item, bool),
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
    }
    return expected in checks and checks[expected](value)


def _require_schema(value: Any, schema: dict[str, Any], label: str) -> None:
    errors = _validate_json_schema(value, schema)
    if errors:
        raise ValueError(f"{label} violates JSON Schema: {'; '.join(errors[:5])}")


def _metric_value(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be an int or float, got {type(value).__name__}")
    metric = float(value)
    if not math.isfinite(metric):
        raise ValueError(f"{label} must be finite")
    if metric <= 0:
        raise ValueError(f"{label} must be strictly positive")
    return metric


def _raw_metric(
    problem: ModuleType,
    instance: dict[str, Any],
    solution: dict[str, Any],
    label: str,
) -> float:
    value = problem.evaluate_solution(instance, solution)
    return _metric_value(value, f"{label} evaluate_solution result")


def _canonical_json(value: Any, label: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} must be JSON serializable: {exc}") from exc


def _smoke_instances(problem: ModuleType) -> list[dict[str, Any]]:
    generated = problem.generate_instances(SMOKE_SEED)
    instances = [generated] if isinstance(generated, dict) else list(generated)
    if len(instances) != INSTANCES_PER_SEED:
        raise RuntimeError(
            f"smoke generator returned {len(instances)} instances; "
            f"expected exactly {INSTANCES_PER_SEED}"
        )
    checked: list[dict[str, Any]] = []
    for instance in instances:
        if not isinstance(instance, dict) or not _finite(instance):
            raise TypeError("smoke instance must be a finite JSON object")
        _require_schema(instance, INPUT_SCHEMA, "smoke instance")
        _canonical_json(instance, "smoke instance")
        checked.append(instance)
    return checked


def _smoke_solver(
    problem: ModuleType,
    solver: Any,
    instance: dict[str, Any],
    label: str,
) -> tuple[dict[str, Any], float]:
    solution = solver(copy.deepcopy(instance))
    if not isinstance(solution, dict) or not _finite(solution):
        raise TypeError(f"{label} output must be a finite JSON object")
    _require_schema(solution, OUTPUT_SCHEMA, f"{label} output")
    _canonical_json(solution, f"{label} output")
    valid, reason = _valid(problem, copy.deepcopy(instance), copy.deepcopy(solution))
    if not valid:
        raise ValueError(f"{label} output is invalid: {reason or 'solution rejected'}")
    metric = _raw_metric(
        problem,
        copy.deepcopy(instance),
        copy.deepcopy(solution),
        label,
    )
    return solution, metric


def _smoke_payload() -> dict[str, Any]:
    problem = _load_module("verification.problem")
    first_instances = _smoke_instances(problem)
    second_instances = _smoke_instances(problem)
    if _canonical_json(first_instances, "generated instances") != _canonical_json(
        second_instances, "repeated generated instances"
    ):
        raise ValueError("generate_instances is not deterministic")

    solvers = (
        ("random solver", problem.solve_random),
        ("baseline solver", problem.solve_baseline),
        ("reference solver", problem.solve_reference),
    )
    solver_runs = 0
    for label, solver in solvers:
        for instance in first_instances:
            first_solution, first_metric = _smoke_solver(problem, solver, instance, label)
            second_solution, second_metric = _smoke_solver(problem, solver, instance, label)
            solver_runs += 2
            if _canonical_json(first_solution, f"{label} output") != _canonical_json(
                second_solution, f"repeated {label} output"
            ):
                raise ValueError(f"{label} is not deterministic")
            if first_metric != second_metric:
                raise ValueError(f"{label} metric is not deterministic")
    return {
        "ok": True,
        "instances_checked": len(first_instances),
        "solver_runs": solver_runs,
        "solvers_checked": [label for label, _solver in solvers],
    }


def _score(baseline: float, candidate: float) -> float:
    if not math.isfinite(baseline) or not math.isfinite(candidate):
        raise ValueError("objective metrics must be finite")
    if baseline <= 0 or candidate <= 0:
        raise ValueError("log2 normalization requires positive metrics")
    ratio = baseline / candidate if DIRECTION == "minimize" else candidate / baseline
    return math.log2(ratio)


def _prepare_payload() -> dict[str, Any]:
    problem = _load_module("verification.problem")
    baseline_module = _load_module("baseline.heuristic")
    baseline_solver = getattr(baseline_module, "solve")  # noqa: B009
    cases: list[dict[str, Any]] = []
    for seed in SEEDS:
        generated = problem.generate_instances(seed)
        instances = [generated] if isinstance(generated, dict) else list(generated)
        if len(instances) != INSTANCES_PER_SEED:
            raise RuntimeError(
                f"seed {seed} generated {len(instances)} instances; "
                f"expected exactly {INSTANCES_PER_SEED}"
            )
        for index, instance in enumerate(instances):
            if not isinstance(instance, dict) or not _finite(instance):
                raise TypeError("generated instance must be a finite JSON object")
            _require_schema(instance, INPUT_SCHEMA, "generated instance")
            baseline_solution = baseline_solver(instance)
            if not isinstance(baseline_solution, dict) or not _finite(baseline_solution):
                raise TypeError("baseline output must be a finite JSON object")
            _require_schema(baseline_solution, OUTPUT_SCHEMA, "baseline output")
            valid, reason = _valid(problem, instance, baseline_solution)
            if not valid:
                raise RuntimeError(f"invalid benchmark baseline: {reason}")
            baseline_metric = _raw_metric(
                problem, instance, baseline_solution, "baseline"
            )
            cases.append(
                {
                    "case_id": f"{seed}:{index}",
                    "seed": seed,
                    "index": index,
                    "instance": instance,
                    "baseline_metric": baseline_metric,
                }
            )
    return {"cases": cases}


def _score_payload(payload: dict[str, Any]) -> dict[str, Any]:
    problem = _load_module("verification.problem")
    prepared = payload.get("prepared", {})
    cases = prepared.get("cases", []) if isinstance(prepared, dict) else []
    submissions = payload.get("submissions", [])
    if not isinstance(cases, list) or not isinstance(submissions, list):
        raise TypeError("score payload must contain cases and submissions lists")
    if len(cases) != len(submissions):
        raise ValueError("submission count does not match prepared case count")
    records: list[dict[str, Any]] = []
    for case, submission in zip(cases, submissions, strict=True):
        started = time.monotonic()
        record = {"case_index": len(records)}
        try:
            if submission.get("case_id") != case.get("case_id"):
                raise ValueError("submission case id mismatch")
            if submission.get("runner_error"):
                raise RuntimeError(str(submission["runner_error"]))
            solution = submission.get("solution")
            if not isinstance(solution, dict) or not _finite(solution):
                raise TypeError("candidate output must be a finite JSON object")
            _require_schema(solution, OUTPUT_SCHEMA, "candidate output")
            instance = case["instance"]
            if not isinstance(instance, dict) or not _finite(instance):
                raise TypeError("prepared instance must be a finite JSON object")
            _require_schema(instance, INPUT_SCHEMA, "prepared instance")
            valid, reason = _valid(problem, instance, solution)
            if not valid:
                raise ValueError(reason or "invalid candidate solution")
            baseline_metric = _metric_value(case["baseline_metric"], "prepared baseline metric")
            candidate_metric = _raw_metric(problem, instance, solution, "candidate")
            record.update(
                valid=True,
                score=_score(baseline_metric, candidate_metric),
                baseline_metric=baseline_metric,
                candidate_metric=candidate_metric,
            )
        except Exception as exc:
            record.update(valid=False, score=INVALID_SCORE, reason=f"{type(exc).__name__}: {exc}")
        record["runtime_s"] = time.monotonic() - started
        records.append(record)
    all_valid = bool(records) and all(record["valid"] for record in records)
    scores = [float(record["score"]) for record in records]
    combined = (
        (statistics.fmean(scores) if AGGREGATION == "mean" else statistics.median(scores))
        if all_valid
        else INVALID_SCORE
    )
    metrics = {
        "valid": 1.0 if all_valid else 0.0,
        "combined_score": combined,
        "instances_total": len(records),
        "instances_valid": sum(bool(record["valid"]) for record in records),
        "runtime_s": sum(float(record["runtime_s"]) for record in records),
    }
    return {"metrics": metrics, "artifacts": {"instance_results": records}}


def _parse_json_result(result: BoundedResult, label: str) -> dict[str, Any]:
    if result.timed_out:
        raise TimeoutError(f"{label} timed out")
    if result.output_truncated:
        raise ValueError(f"{label} exceeded output limit")
    if result.returncode != 0:
        raise RuntimeError(f"{label} exited with {result.returncode}: {result.stderr[-2000:]}")
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or not _finite(value):
        raise TypeError(f"{label} output must be a finite JSON object")
    return value


def _candidate_local(
    candidate: Path,
    instance: dict[str, Any],
    *,
    timeout_s: float = TIMEOUT_S,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> dict[str, Any]:
    result = run_bounded(
        [sys.executable, str(candidate)],
        json.dumps(instance, allow_nan=False),
        timeout_s=timeout_s,
        max_output_bytes=max_output_bytes,
    )
    return _parse_json_result(result, "candidate")


def _docker_base(name: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--user",
        "65532:65532",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        str(PIDS_LIMIT),
        "--memory",
        f"{MEMORY_MB}m",
        "--cpus",
        str(CPUS),
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",
    ]


def _docker_json(
    command: list[str],
    input_payload: dict[str, Any] | None,
    *,
    timeout_s: float,
    label: str,
    max_output_bytes: int = 2_000_000,
) -> dict[str, Any]:
    name = f"benchgen-{label}-{uuid.uuid4().hex[:12]}"
    full_command = _docker_base(name) + command
    result = run_bounded(
        full_command,
        json.dumps(input_payload, allow_nan=False) if input_payload is not None else "",
        timeout_s=timeout_s,
        max_output_bytes=max_output_bytes,
    )
    if result.timed_out:
        run_bounded(
            ["docker", "rm", "--force", name],
            "",
            timeout_s=10,
            max_output_bytes=10_000,
        )
    return _parse_json_result(result, label)


def _verifier_container(mode: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if "," in str(ROOT) or "\n" in str(ROOT):
        raise ValueError("benchmark path contains unsupported Docker mount characters")
    command: list[str] = []
    for relative in ("verification", "baseline", "reference", "data", "references"):
        source = ROOT / relative
        if source.exists():
            command.extend(
                (
                    "--mount",
                    f"type=bind,src={source},dst=/workspace/benchmark/{relative},readonly",
                )
            )
    command.extend(
        (
            "--workdir",
            "/workspace/benchmark",
            RUNTIME_IMAGE,
            "python",
            "/workspace/benchmark/verification/evaluator.py",
            mode,
        )
    )
    return _docker_json(command, payload, timeout_s=130.0, label="verifier")


def _candidate_container(
    candidate: Path,
    case: dict[str, Any],
    *,
    timeout_s: float = TIMEOUT_S,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> dict[str, Any]:
    if "," in str(candidate) or "\n" in str(candidate):
        raise ValueError("candidate path contains unsupported Docker mount characters")
    trusted_solver = False
    try:
        relative = candidate.relative_to(ROOT)
        trusted_solver = bool(relative.parts and relative.parts[0] in {"baseline", "reference"})
    except ValueError:
        relative = Path(candidate.name)
    if trusted_solver:
        command = [
            "--mount",
            f"type=bind,src={ROOT},dst=/workspace/benchmark,readonly",
            "--workdir",
            "/workspace/benchmark",
            RUNTIME_IMAGE,
            "python",
            f"/workspace/benchmark/{relative.as_posix()}",
        ]
    else:
        command = [
            "--mount",
            f"type=bind,src={candidate},dst=/workspace/candidate.py,readonly",
            "--workdir",
            "/tmp",
            RUNTIME_IMAGE,
            "python",
            "/workspace/candidate.py",
        ]
    return _docker_json(
        command,
        case["instance"],
        timeout_s=timeout_s,
        label="candidate",
        max_output_bytes=max_output_bytes,
    )


def evaluate(
    candidate: Path,
    *,
    local: bool = False,
    candidate_timeout_s: float = TIMEOUT_S,
    candidate_max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise FileNotFoundError(f"candidate not found: {candidate}")
    if local:
        prepared = _prepare_payload()
        submissions = []
        for case in prepared["cases"]:
            try:
                solution = _candidate_local(
                    candidate,
                    case["instance"],
                    timeout_s=candidate_timeout_s,
                    max_output_bytes=candidate_max_output_bytes,
                )
                submissions.append({"case_id": case["case_id"], "solution": solution})
            except Exception as exc:
                submissions.append(
                    {"case_id": case["case_id"], "runner_error": f"{type(exc).__name__}: {exc}"}
                )
        result = _score_payload({"prepared": prepared, "submissions": submissions})
    else:
        prepared = _verifier_container("--prepare")
        submissions = []
        for case in prepared["cases"]:
            try:
                solution = _candidate_container(
                    candidate,
                    case,
                    timeout_s=candidate_timeout_s,
                    max_output_bytes=candidate_max_output_bytes,
                )
                submissions.append({"case_id": case["case_id"], "solution": solution})
            except Exception as exc:
                submissions.append(
                    {"case_id": case["case_id"], "runner_error": f"{type(exc).__name__}: {exc}"}
                )
        result = _verifier_container(
            "--score", {"prepared": prepared, "submissions": submissions}
        )
    return result["metrics"], result["artifacts"]


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    from tempfile import NamedTemporaryFile

    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.replace(path)


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--smoke":
        try:
            payload = _verifier_container("--smoke-local")
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            print(json.dumps({"ok": False, "error": message}, sort_keys=True))
            print(message, file=sys.stderr)
            return 1
        print(json.dumps(payload, sort_keys=True, allow_nan=False))
        return 0
    if len(sys.argv) == 2 and sys.argv[1] == "--smoke-local":
        try:
            payload = _smoke_payload()
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            print(json.dumps({"ok": False, "error": message}, sort_keys=True))
            print(message, file=sys.stderr)
            return 1
        print(json.dumps(payload, sort_keys=True, allow_nan=False))
        return 0
    if len(sys.argv) == 2 and sys.argv[1] == "--prepare":
        print(json.dumps(_prepare_payload(), sort_keys=True, allow_nan=False))
        return 0
    if len(sys.argv) == 2 and sys.argv[1] == "--score":
        payload = json.load(sys.stdin)
        print(json.dumps(_score_payload(payload), sort_keys=True, allow_nan=False))
        return 0
    parser = argparse.ArgumentParser(description="Evaluate one structured-solution candidate.")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--local", action="store_true")
    parser.add_argument(
        "--_benchgen-probe-timeout-s",
        type=float,
        default=TIMEOUT_S,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--_benchgen-probe-max-output-bytes",
        type=int,
        default=MAX_OUTPUT_BYTES,
        help=argparse.SUPPRESS,
    )
    arguments = parser.parse_args()
    if not 0 < arguments._benchgen_probe_timeout_s <= TIMEOUT_S:
        parser.error("probe timeout must be positive and cannot relax the benchmark limit")
    if not 0 < arguments._benchgen_probe_max_output_bytes <= MAX_OUTPUT_BYTES:
        parser.error("probe output limit must be positive and cannot relax the benchmark limit")
    metrics, artifacts = evaluate(
        arguments.candidate,
        local=arguments.local,
        candidate_timeout_s=arguments._benchgen_probe_timeout_s,
        candidate_max_output_bytes=arguments._benchgen_probe_max_output_bytes,
    )
    _atomic_json(Path.cwd() / "metrics.json", metrics)
    _atomic_json(Path.cwd() / "artifacts.json", artifacts)
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
