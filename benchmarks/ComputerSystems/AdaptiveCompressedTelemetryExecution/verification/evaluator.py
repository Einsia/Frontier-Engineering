"""Compile and benchmark adaptive compressed telemetry execution candidates."""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import random
import resource
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any


TASK_DIR = Path(__file__).resolve().parents[1]
VERIFICATION_DIR = TASK_DIR / "verification"
DRIVER_SOURCE = VERIFICATION_DIR / "benchmark_driver.cpp"
API_HEADER = VERIFICATION_DIR / "codec_api.h"
BASELINE_SOURCE = TASK_DIR / "baseline" / "solution.cpp"
PROBLEM_PATH = TASK_DIR / "references" / "problem_config.json"
RAW_MAGIC = b"TELRAW01"
UINT64_BYTES = 8
COLUMN_COUNT = 5
TIB_BYTES = 1 << 40
MAX_TEXT_CAPTURE = 12_000


class EvaluationFailure(RuntimeError):
    def __init__(self, message: str, *, timeout: bool = False) -> None:
        super().__init__(message)
        self.timeout = timeout


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_constant,
    )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _positive_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be a positive finite number")
    return result


def _load_problem() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    problem = _object(_load_json(PROBLEM_PATH), "problem configuration")
    if str(problem.get("benchmark_id", "")) != "adaptive_compressed_telemetry_execution":
        raise ValueError("unexpected benchmark_id")
    execution = _object(problem.get("execution"), "execution")
    pricing = _object(problem.get("pricing"), "pricing")
    scenarios_raw = problem.get("scenarios")
    if not isinstance(scenarios_raw, list) or not scenarios_raw:
        raise ValueError("scenarios must be a non-empty list")
    scenarios: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(scenarios_raw):
        scenario = _object(raw, f"scenarios[{index}]")
        scenario_id = str(scenario.get("id", "")).strip()
        if not scenario_id or scenario_id in seen:
            raise ValueError(f"invalid or duplicate scenario id: {scenario_id!r}")
        seen.add(scenario_id)
        if str(scenario.get("pattern", "")) not in {"steady", "bursty", "incident"}:
            raise ValueError(f"scenario {scenario_id} has an unsupported pattern")
        _positive_int(scenario.get("rows"), f"scenario {scenario_id}.rows")
        _positive_int(scenario.get("seed"), f"scenario {scenario_id}.seed")
        _positive_number(
            scenario.get("monthly_full_decodes"),
            f"scenario {scenario_id}.monthly_full_decodes",
        )
        _positive_number(
            scenario.get("monthly_query_batches"),
            f"scenario {scenario_id}.monthly_query_batches",
        )
        scenarios.append(scenario)

    for key in (
        "block_rows",
        "warmup_rounds",
        "measured_rounds",
        "compile_timeout_s",
        "run_timeout_s",
        "source_limit_bytes",
        "memory_limit_mb",
    ):
        _positive_int(execution.get(key), f"execution.{key}")
    _positive_number(execution.get("max_encoded_ratio"), "execution.max_encoded_ratio")
    _positive_number(
        pricing.get("storage_dollars_per_gib_month"),
        "pricing.storage_dollars_per_gib_month",
    )
    _positive_number(
        pricing.get("cpu_dollars_per_core_hour"),
        "pricing.cpu_dollars_per_core_hour",
    )
    return problem, execution, pricing, scenarios


def _severity(rng: random.Random, *, incident: bool = False) -> int:
    roll = rng.randrange(1000)
    if incident:
        if roll < 430:
            return 17
        if roll < 520:
            return 21
        if roll < 720:
            return 13
        return 9
    if roll < 885:
        return 9
    if roll < 950:
        return 13
    if roll < 993:
        return 17
    return 21


def _generate_columns(scenario: dict[str, Any], evaluation_seed: int) -> list[array.array[int]]:
    rows = _positive_int(scenario.get("rows"), "scenario.rows")
    seed = _positive_int(scenario.get("seed"), "scenario.seed") ^ evaluation_seed
    rng = random.Random(seed)
    pattern = str(scenario["pattern"])
    columns = [array.array("Q") for _ in range(COLUMN_COUNT)]
    timestamp = 1_700_000_000_000_000_000 + (seed % 10_000_000)
    payload_choices = (128, 256, 384, 512, 768, 1024, 2048, 4096, 8192)

    timestamp_col, service_col, severity_col, duration_col, payload_col = columns
    for row in range(rows):
        if pattern == "steady":
            timestamp += 850_000 + rng.randrange(300_001)
            service = (row * 17 + rng.randrange(5)) % 32
            severity = _severity(rng)
            duration = 75 + rng.randrange(650) + (service % 5) * 23
            if severity >= 17:
                duration += 800 + rng.randrange(2200)
            payload = payload_choices[(service + rng.randrange(4)) % len(payload_choices)]
        elif pattern == "bursty":
            burst = row // 4096
            timestamp += 90_000 + rng.randrange(180_001)
            if row % 4096 == 0:
                timestamp += 8_000_000 + rng.randrange(20_000_000)
            hot_service = (burst * 73 + 11) % 512
            service = hot_service if rng.randrange(100) < 72 else rng.randrange(512)
            severity = _severity(rng, incident=(burst % 11 == 7 and row % 17 < 5))
            duration = 110 + rng.randrange(1600) + (service % 13) * 19
            if service == hot_service:
                duration //= 2
            if severity >= 17:
                duration += 2500 + rng.randrange(7000)
            payload = payload_choices[(service ^ burst ^ rng.randrange(8)) % len(payload_choices)]
        else:
            phase = (row * 10) // rows
            active_incident = 5 <= phase <= 7
            timestamp += 600_000 + rng.randrange(800_001)
            if row % 16384 == 0:
                timestamp += 50_000_000 + rng.randrange(100_000_000)
            base_service = (row // 128 + phase * 29) % 96
            if active_incident and rng.randrange(100) < 62:
                service = 77
            else:
                service = (base_service + rng.randrange(9)) % 96
            severity = _severity(rng, incident=active_incident and service == 77)
            duration = 60 + rng.randrange(900) + (service % 8) * 31
            if active_incident and service == 77:
                duration += 8_000 + rng.randrange(45_000)
            elif severity >= 17:
                duration += 1_000 + rng.randrange(5_000)
            payload = payload_choices[(phase + service + rng.randrange(5)) % len(payload_choices)]

        timestamp_col.append(timestamp)
        service_col.append(service)
        severity_col.append(severity)
        duration_col.append(duration)
        payload_col.append(payload)
    return columns


def _quantile(values: array.array[int], fraction: float) -> int:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction)))
    return int(ordered[index])


def _build_queries(columns: list[array.array[int]]) -> list[dict[str, Any]]:
    timestamp, service, severity, duration, _payload = columns
    hot_service = int(Counter(service).most_common(1)[0][0])
    max_service = int(max(service))
    queries = [
        {
            "name": "hot_service_count",
            "kind": 0,
            "filter_column": 1,
            "value_column": 1,
            "low": hot_service,
            "high": hot_service,
        },
        {
            "name": "error_count",
            "kind": 1,
            "filter_column": 2,
            "value_column": 2,
            "low": 17,
            "high": 24,
        },
        {
            "name": "hot_service_duration",
            "kind": 2,
            "filter_column": 1,
            "value_column": 3,
            "low": hot_service,
            "high": hot_service,
        },
        {
            "name": "error_payload",
            "kind": 3,
            "filter_column": 2,
            "value_column": 4,
            "low": 17,
            "high": 24,
        },
        {
            "name": "middle_window_count",
            "kind": 1,
            "filter_column": 0,
            "value_column": 0,
            "low": int(timestamp[len(timestamp) // 4]),
            "high": int(timestamp[(3 * len(timestamp)) // 4]),
        },
        {
            "name": "low_service_duration",
            "kind": 3,
            "filter_column": 1,
            "value_column": 3,
            "low": 0,
            "high": max(1, max_service // 8),
        },
        {
            "name": "middle_latency_count",
            "kind": 1,
            "filter_column": 3,
            "value_column": 3,
            "low": _quantile(duration, 0.40),
            "high": _quantile(duration, 0.75),
        },
        {
            "name": "window_payload",
            "kind": 3,
            "filter_column": 0,
            "value_column": 4,
            "low": int(timestamp[len(timestamp) // 3]),
            "high": int(timestamp[(2 * len(timestamp)) // 3]),
        },
    ]
    for query in queries:
        filter_values = columns[int(query["filter_column"])]
        value_values = columns[int(query["value_column"])]
        kind = int(query["kind"])
        low = int(query["low"])
        high = int(query["high"])
        result = 0
        if kind == 0:
            result = sum(1 for value in filter_values if value == low)
        elif kind == 1:
            result = sum(1 for value in filter_values if low <= value <= high)
        elif kind == 2:
            result = sum(
                int(value_values[index])
                for index, value in enumerate(filter_values)
                if value == low
            )
        elif kind == 3:
            result = sum(
                int(value_values[index])
                for index, value in enumerate(filter_values)
                if low <= value <= high
            )
        query["expected"] = int(result)
    return queries


def _write_raw(path: Path, columns: list[array.array[int]]) -> None:
    rows = len(columns[0])
    if any(len(column) != rows for column in columns):
        raise ValueError("generated columns have different lengths")
    with path.open("wb") as handle:
        handle.write(RAW_MAGIC)
        handle.write(struct.pack("<Q", rows))
        for column in columns:
            values = array.array("Q", column)
            if sys.byteorder != "little":
                values.byteswap()
            values.tofile(handle)


def _write_queries(path: Path, queries: list[dict[str, Any]]) -> None:
    lines = [
        "\t".join(
            str(value)
            for value in (
                query["name"],
                query["kind"],
                query["filter_column"],
                query["value_column"],
                query["low"],
                query["high"],
            )
        )
        for query in queries
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _compile(
    compiler: str,
    source: Path,
    output: Path,
    timeout_s: int,
) -> dict[str, Any]:
    command = [
        compiler,
        "-std=c++20",
        "-O3",
        "-DNDEBUG",
        "-march=native",
        "-I",
        str(VERIFICATION_DIR),
        str(DRIVER_SOURCE),
        str(source),
        "-o",
        str(output),
    ]
    started = time.perf_counter()
    try:
        process = subprocess.run(
            command,
            cwd=str(TASK_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise EvaluationFailure(
            f"compilation timed out after {timeout_s}s",
            timeout=True,
        ) from exc
    result = {
        "command": command,
        "returncode": process.returncode,
        "runtime_s": time.perf_counter() - started,
        "stdout": process.stdout[-MAX_TEXT_CAPTURE:],
        "stderr": process.stderr[-MAX_TEXT_CAPTURE:],
    }
    if process.returncode != 0 or not output.is_file():
        raise EvaluationFailure(
            "candidate compilation failed:\n" + process.stderr[-MAX_TEXT_CAPTURE:]
        )
    return result


def _preexec_limits(memory_limit_mb: int, cpu: int | None, timeout_s: int) -> Any:
    def apply() -> None:
        memory_bytes = memory_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        cpu_limit = max(2, int(math.ceil(timeout_s)))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 1))
        file_limit = 512 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
        if cpu is not None and hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, {cpu})

    return apply


def _parse_driver_metrics(path: Path) -> dict[str, float]:
    if not path.is_file():
        raise EvaluationFailure("benchmark driver did not write its metrics file")
    metrics: dict[str, float] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        if "=" not in raw_line:
            raise EvaluationFailure(f"invalid driver metric row: {raw_line}")
        key, raw_value = raw_line.split("=", 1)
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise EvaluationFailure(f"invalid driver metric {key}") from exc
        if not math.isfinite(value):
            raise EvaluationFailure(f"non-finite driver metric {key}")
        metrics[key] = value
    for required in ("median_ns", "min_ns", "max_ns", "logical_bytes"):
        if metrics.get(required, 0.0) <= 0.0:
            raise EvaluationFailure(f"driver metric {required} is missing or non-positive")
    return metrics


def _run_driver(
    binary: Path,
    arguments: list[str],
    metrics_path: Path,
    *,
    cwd: Path,
    timeout_s: int,
    memory_limit_mb: int,
    cpu: int | None,
) -> tuple[dict[str, float], dict[str, Any]]:
    cwd.mkdir(parents=True, exist_ok=True)
    command = [str(binary), *arguments]
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    started = time.perf_counter()
    try:
        process = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=environment,
            preexec_fn=_preexec_limits(memory_limit_mb, cpu, timeout_s),
        )
    except subprocess.TimeoutExpired as exc:
        raise EvaluationFailure(
            f"benchmark driver timed out after {timeout_s}s",
            timeout=True,
        ) from exc
    record = {
        "command": command,
        "returncode": process.returncode,
        "runtime_s": time.perf_counter() - started,
        "stdout": process.stdout[-MAX_TEXT_CAPTURE:],
        "stderr": process.stderr[-MAX_TEXT_CAPTURE:],
    }
    if process.returncode != 0:
        raise EvaluationFailure(
            "benchmark driver failed:\n" + process.stderr[-MAX_TEXT_CAPTURE:]
        )
    return _parse_driver_metrics(metrics_path), record


def _read_query_results(path: Path) -> dict[str, int]:
    if not path.is_file():
        raise EvaluationFailure("benchmark driver did not write query results")
    results: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or not parts[0] or parts[0] in results:
            raise EvaluationFailure(f"invalid query result row: {line}")
        try:
            results[parts[0]] = int(parts[1])
        except ValueError as exc:
            raise EvaluationFailure(f"invalid query result value: {line}") from exc
    return results


def _economic_cost(
    encode: dict[str, float],
    decode: dict[str, float],
    query: dict[str, float],
    scenario: dict[str, Any],
    pricing: dict[str, Any],
) -> dict[str, float]:
    logical_bytes = encode["logical_bytes"]
    if (
        abs(decode["logical_bytes"] - logical_bytes) > 0.5
        or abs(query["logical_bytes"] - logical_bytes) > 0.5
    ):
        raise EvaluationFailure("driver phases disagree on logical byte count")
    encoded_bytes = encode.get("encoded_bytes", 0.0)
    if encoded_bytes <= 0.0:
        raise EvaluationFailure("encoded byte count is missing")
    scale_to_tib = TIB_BYTES / logical_bytes
    ns_to_core_hours_per_tib = scale_to_tib / (1e9 * 3600.0)
    compression_ratio = encoded_bytes / logical_bytes
    encode_hours = encode["median_ns"] * ns_to_core_hours_per_tib
    decode_hours = decode["median_ns"] * ns_to_core_hours_per_tib
    query_hours = query["median_ns"] * ns_to_core_hours_per_tib
    storage_cost = (
        1024.0
        * compression_ratio
        * _positive_number(
            pricing.get("storage_dollars_per_gib_month"),
            "storage_dollars_per_gib_month",
        )
    )
    cpu_price = _positive_number(
        pricing.get("cpu_dollars_per_core_hour"),
        "cpu_dollars_per_core_hour",
    )
    cpu_cost = cpu_price * (
        encode_hours
        + _positive_number(
            scenario.get("monthly_full_decodes"), "monthly_full_decodes"
        )
        * decode_hours
        + _positive_number(
            scenario.get("monthly_query_batches"), "monthly_query_batches"
        )
        * query_hours
    )
    total = storage_cost + cpu_cost
    if not math.isfinite(total) or total <= 0.0:
        raise EvaluationFailure("economic cost is not positive and finite")
    return {
        "monthly_cost_per_logical_tib": total,
        "storage_cost": storage_cost,
        "cpu_cost": cpu_cost,
        "compression_ratio": compression_ratio,
        "encode_core_hours_per_tib": encode_hours,
        "decode_core_hours_per_tib": decode_hours,
        "query_batch_core_hours_per_tib": query_hours,
    }


def _invalid_metrics(started: float, *, timeout: bool = False) -> dict[str, float]:
    return {
        "combined_score": 0.0,
        "valid": 0.0,
        "correctness": 0.0,
        "timeout": 1.0 if timeout else 0.0,
        "runtime_s": time.perf_counter() - started,
    }


def evaluate(
    candidate_path: Path,
    *,
    seed_override: int | None = None,
    timeout_override: int | None = None,
) -> tuple[dict[str, float], dict[str, Any]]:
    started = time.perf_counter()
    artifacts: dict[str, Any] = {
        "benchmark_id": "adaptive_compressed_telemetry_execution",
        "candidate_path": str(candidate_path),
    }
    try:
        problem, execution, pricing, scenarios = _load_problem()
        if not candidate_path.is_file():
            raise EvaluationFailure(f"candidate source not found: {candidate_path}")
        if not BASELINE_SOURCE.is_file() or not DRIVER_SOURCE.is_file() or not API_HEADER.is_file():
            raise EvaluationFailure("immutable benchmark source is missing")
        source_limit = _positive_int(
            execution.get("source_limit_bytes"), "execution.source_limit_bytes"
        )
        if candidate_path.stat().st_size > source_limit:
            raise EvaluationFailure(
                f"candidate source exceeds {source_limit} bytes"
            )
        compiler = shutil.which("g++")
        if not compiler:
            raise EvaluationFailure("g++ is required but was not found")

        candidate_matches_baseline = (
            candidate_path.read_bytes() == BASELINE_SOURCE.read_bytes()
        )
        artifacts["candidate_source_matches_baseline"] = candidate_matches_baseline
        evaluation_seed = (
            int(seed_override)
            if seed_override is not None
            else _positive_int(problem.get("evaluation_seed"), "evaluation_seed")
        )
        artifacts["evaluation_seed"] = evaluation_seed
        available_cpus: list[int] = []
        if hasattr(os, "sched_getaffinity"):
            available_cpus = sorted(os.sched_getaffinity(0))
        pinned_cpu = available_cpus[0] if available_cpus else None
        artifacts["pinned_cpu"] = pinned_cpu

        compile_timeout = _positive_int(
            execution.get("compile_timeout_s"), "execution.compile_timeout_s"
        )
        run_timeout = (
            int(timeout_override)
            if timeout_override is not None
            else _positive_int(execution.get("run_timeout_s"), "execution.run_timeout_s")
        )
        if run_timeout <= 0:
            raise EvaluationFailure("run timeout must be positive")
        memory_limit_mb = _positive_int(
            execution.get("memory_limit_mb"), "execution.memory_limit_mb"
        )
        block_rows = _positive_int(execution.get("block_rows"), "execution.block_rows")
        warmup_rounds = _positive_int(
            execution.get("warmup_rounds"), "execution.warmup_rounds"
        )
        measured_rounds = _positive_int(
            execution.get("measured_rounds"), "execution.measured_rounds"
        )
        max_encoded_ratio = _positive_number(
            execution.get("max_encoded_ratio"), "execution.max_encoded_ratio"
        )

        with tempfile.TemporaryDirectory(prefix="adaptive_telemetry_eval_") as tmp_text:
            tmp = Path(tmp_text)
            candidate_binary = tmp / "candidate_driver"
            artifacts["candidate_compile"] = _compile(
                compiler, candidate_path, candidate_binary, compile_timeout
            )
            baseline_binary = candidate_binary
            if not candidate_matches_baseline:
                baseline_binary = tmp / "baseline_driver"
                artifacts["baseline_compile"] = _compile(
                    compiler, BASELINE_SOURCE, baseline_binary, compile_timeout
                )
            binaries = {
                "candidate": candidate_binary,
                "baseline": baseline_binary,
            }

            scenario_artifacts: dict[str, Any] = {}
            ratios: list[float] = []
            total_logical_bytes = 0.0
            candidate_encoded_bytes = 0.0
            candidate_encode_ns = 0.0
            candidate_decode_ns = 0.0
            candidate_query_ns = 0.0
            baseline_total_cost = 0.0
            candidate_total_cost = 0.0
            for scenario_index, scenario in enumerate(scenarios):
                scenario_id = str(scenario["id"])
                scenario_dir = tmp / scenario_id
                scenario_dir.mkdir()
                columns = _generate_columns(scenario, evaluation_seed)
                queries = _build_queries(columns)
                raw_path = scenario_dir / "input.raw"
                query_path = scenario_dir / "queries.tsv"
                _write_raw(raw_path, columns)
                _write_queries(query_path, queries)
                raw_payload = raw_path.read_bytes()
                raw_sha256 = hashlib.sha256(raw_payload).hexdigest()
                expected_queries = {
                    str(query["name"]): int(query["expected"]) for query in queries
                }
                del columns

                labels = ["candidate"] if candidate_matches_baseline else ["baseline", "candidate"]
                if not candidate_matches_baseline and scenario_index % 2 == 1:
                    labels.reverse()
                phase_metrics: dict[str, dict[str, dict[str, float]]] = {}
                phase_runs: dict[str, dict[str, Any]] = {}
                encoded_paths: dict[str, Path] = {}
                for label in labels:
                    label_dir = scenario_dir / label
                    label_dir.mkdir()
                    encoded_path = label_dir / "encoded.bin"
                    encode_metrics_path = label_dir / "encode.metrics"
                    encode_metrics, encode_run = _run_driver(
                        binaries[label],
                        [
                            "encode",
                            str(raw_path),
                            str(encoded_path),
                            str(encode_metrics_path),
                            str(block_rows),
                            str(warmup_rounds),
                            str(measured_rounds),
                            str(max_encoded_ratio),
                        ],
                        encode_metrics_path,
                        cwd=label_dir / "encode_work",
                        timeout_s=run_timeout,
                        memory_limit_mb=memory_limit_mb,
                        cpu=pinned_cpu,
                    )
                    phase_metrics[label] = {"encode": encode_metrics}
                    phase_runs[label] = {"encode": encode_run}
                    encoded_paths[label] = encoded_path

                # Decoding happens in a fresh process after the original input has
                # been removed, so candidate globals or file references cannot serve
                # as a substitute for a self-contained encoded representation.
                raw_path.unlink()
                for label in labels:
                    label_dir = scenario_dir / label
                    decoded_path = label_dir / "decoded.raw"
                    decode_metrics_path = label_dir / "decode.metrics"
                    decode_metrics, decode_run = _run_driver(
                        binaries[label],
                        [
                            "decode",
                            str(encoded_paths[label]),
                            str(decoded_path),
                            str(decode_metrics_path),
                            str(warmup_rounds),
                            str(measured_rounds),
                        ],
                        decode_metrics_path,
                        cwd=label_dir / "decode_work",
                        timeout_s=run_timeout,
                        memory_limit_mb=memory_limit_mb,
                        cpu=pinned_cpu,
                    )
                    if not decoded_path.is_file() or decoded_path.read_bytes() != raw_payload:
                        raise EvaluationFailure(
                            f"{scenario_id}: {label} decode does not exactly match input"
                        )
                    decoded_path.unlink()

                    query_results_path = label_dir / "query_results.tsv"
                    query_metrics_path = label_dir / "query.metrics"
                    query_metrics, query_run = _run_driver(
                        binaries[label],
                        [
                            "query",
                            str(encoded_paths[label]),
                            str(query_path),
                            str(query_results_path),
                            str(query_metrics_path),
                            str(warmup_rounds),
                            str(measured_rounds),
                        ],
                        query_metrics_path,
                        cwd=label_dir / "query_work",
                        timeout_s=run_timeout,
                        memory_limit_mb=memory_limit_mb,
                        cpu=pinned_cpu,
                    )
                    actual_queries = _read_query_results(query_results_path)
                    if actual_queries != expected_queries:
                        mismatches = {
                            key: {
                                "expected": expected_queries.get(key),
                                "actual": actual_queries.get(key),
                            }
                            for key in sorted(set(expected_queries) | set(actual_queries))
                            if expected_queries.get(key) != actual_queries.get(key)
                        }
                        raise EvaluationFailure(
                            f"{scenario_id}: {label} compressed query mismatch: {mismatches}"
                        )
                    phase_metrics[label]["decode"] = decode_metrics
                    phase_metrics[label]["query"] = query_metrics
                    phase_runs[label]["decode"] = decode_run
                    phase_runs[label]["query"] = query_run

                if candidate_matches_baseline:
                    phase_metrics["baseline"] = phase_metrics["candidate"]
                    phase_runs["baseline"] = phase_runs["candidate"]

                costs = {
                    label: _economic_cost(
                        phase_metrics[label]["encode"],
                        phase_metrics[label]["decode"],
                        phase_metrics[label]["query"],
                        scenario,
                        pricing,
                    )
                    for label in ("baseline", "candidate")
                }
                ratio = (
                    costs["baseline"]["monthly_cost_per_logical_tib"]
                    / costs["candidate"]["monthly_cost_per_logical_tib"]
                )
                if not math.isfinite(ratio) or ratio <= 0.0:
                    raise EvaluationFailure(f"{scenario_id}: invalid score ratio")
                ratios.append(ratio)
                baseline_total_cost += costs["baseline"]["monthly_cost_per_logical_tib"]
                candidate_total_cost += costs["candidate"]["monthly_cost_per_logical_tib"]

                candidate_encode = phase_metrics["candidate"]["encode"]
                candidate_decode = phase_metrics["candidate"]["decode"]
                candidate_query = phase_metrics["candidate"]["query"]
                total_logical_bytes += candidate_encode["logical_bytes"]
                candidate_encoded_bytes += candidate_encode["encoded_bytes"]
                candidate_encode_ns += candidate_encode["median_ns"]
                candidate_decode_ns += candidate_decode["median_ns"]
                candidate_query_ns += candidate_query["median_ns"]
                scenario_artifacts[scenario_id] = {
                    "pattern": scenario["pattern"],
                    "rows": scenario["rows"],
                    "dataset_sha256": raw_sha256,
                    "query_expected": expected_queries,
                    "score_ratio": ratio,
                    "baseline": {
                        "measurements": phase_metrics["baseline"],
                        "economic_cost": costs["baseline"],
                    },
                    "candidate": {
                        "measurements": phase_metrics["candidate"],
                        "economic_cost": costs["candidate"],
                    },
                    "driver_runs": phase_runs,
                }

            combined_score = math.exp(
                sum(math.log(value) for value in ratios) / len(ratios)
            )
            seconds_per_ns = 1e-9
            gib = 1 << 30
            metrics = {
                "combined_score": combined_score,
                "valid": 1.0,
                "correctness": 1.0,
                "timeout": 0.0,
                "runtime_s": time.perf_counter() - started,
                "scenario_count": float(len(ratios)),
                "mean_score_ratio": sum(ratios) / len(ratios),
                "min_score_ratio": min(ratios),
                "candidate_total_monthly_cost_per_tib": candidate_total_cost,
                "baseline_total_monthly_cost_per_tib": baseline_total_cost,
                "candidate_compression_ratio": candidate_encoded_bytes
                / total_logical_bytes,
                "candidate_encode_gib_s": total_logical_bytes
                / gib
                / (candidate_encode_ns * seconds_per_ns),
                "candidate_decode_gib_s": total_logical_bytes
                / gib
                / (candidate_decode_ns * seconds_per_ns),
                "candidate_query_batch_gib_s": total_logical_bytes
                / gib
                / (candidate_query_ns * seconds_per_ns),
                "candidate_source_matches_baseline": 1.0
                if candidate_matches_baseline
                else 0.0,
            }
            artifacts["scenario_results"] = scenario_artifacts
            artifacts["pricing"] = pricing
            artifacts["execution"] = execution
            artifacts["timing_note"] = (
                "All candidate functions were timed in compiled, CPU-pinned child "
                "processes; file loading, result writing, and compilation were excluded."
            )
            return metrics, artifacts
    except EvaluationFailure as exc:
        artifacts["error_message"] = str(exc)
        return _invalid_metrics(started, timeout=exc.timeout), artifacts
    except Exception as exc:
        artifacts["error_message"] = f"evaluator error: {type(exc).__name__}: {exc}"
        return _invalid_metrics(started), artifacts


def _write_json(path_text: str | None, payload: dict[str, Any]) -> None:
    if not path_text:
        return
    path = Path(path_text).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", help="candidate C++ source")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--timeout-s", type=int, default=None)
    parser.add_argument("--metrics-out", default=None)
    parser.add_argument("--artifacts-out", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metrics, artifacts = evaluate(
        Path(args.candidate).expanduser().resolve(),
        seed_override=args.seed,
        timeout_override=args.timeout_s,
    )
    _write_json(args.metrics_out, metrics)
    _write_json(args.artifacts_out, artifacts)
    print(json.dumps(metrics, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
