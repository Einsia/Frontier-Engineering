from __future__ import annotations

import argparse
import json
import math
import os
import select
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from pypower.idx_bus import VM, VMAX, VMIN
from pypower.idx_gen import GEN_BUS, GEN_STATUS, PG, PMAX, PMIN, VG


TASK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK_ROOT))

from verification.grid_utils import (  # noqa: E402
    apply_scenario,
    assess_result,
    generation_cost,
    load_case,
    public_payload,
    run_candidate_pf,
)


WORKER_PATH = TASK_ROOT / "verification" / "candidate_worker.py"
IMPORT_TIMEOUT_S = 10.0
SOLVE_TIMEOUT_S = 2.0


def _terminate_worker(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=1.0)


def _read_json_line(process: subprocess.Popen[str], timeout_s: float, stage: str) -> dict[str, Any]:
    assert process.stdout is not None
    ready, _, _ = select.select([process.stdout], [], [], timeout_s)
    if not ready:
        _terminate_worker(process)
        raise TimeoutError(f"candidate {stage} exceeded {timeout_s:g} seconds")
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read().strip() if process.stderr is not None else ""
        raise RuntimeError(f"candidate worker exited during {stage}: {stderr[:500]}")
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"candidate worker emitted invalid JSON during {stage}") from exc
    if not isinstance(message, dict):
        raise TypeError(f"candidate worker emitted a non-object during {stage}")
    return message


def run_candidate(candidate_path: Path, payload: dict[str, Any]) -> Any:
    with tempfile.TemporaryDirectory(prefix="frontier-scd-candidate-") as temp_dir:
        isolated_candidate = Path(temp_dir) / "candidate.py"
        shutil.copyfile(candidate_path, isolated_candidate)
        environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        }
        process = subprocess.Popen(
            [sys.executable, "-I", str(WORKER_PATH), str(isolated_candidate)],
            cwd=temp_dir,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            start_new_session=True,
        )
        try:
            message = _read_json_line(process, IMPORT_TIMEOUT_S, "import")
            if message.get("status") != "ready":
                raise RuntimeError(str(message.get("error", "candidate import failed")))
            assert process.stdin is not None
            process.stdin.write(json.dumps(payload, allow_nan=False, separators=(",", ":")) + "\n")
            process.stdin.flush()
            message = _read_json_line(process, SOLVE_TIMEOUT_S + 0.25, "solve")
            if message.get("status") != "ok":
                raise RuntimeError(str(message.get("error", "candidate solve failed")))
            return message.get("output")
        finally:
            _terminate_worker(process)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def parse_output(output: Any, mpc: dict[str, Any], payload: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(output, dict):
        raise TypeError("solve(case) must return a dictionary")
    if "pg_mw" not in output or "vg_pu" not in output:
        raise ValueError("candidate output must contain both pg_mw and vg_pu")
    pg = np.asarray(output["pg_mw"], dtype=float)
    vg = np.asarray(output["vg_pu"], dtype=float)
    generator_count = len(mpc["gen"])
    if pg.shape != (generator_count,) or vg.shape != (generator_count,):
        raise ValueError(f"pg_mw and vg_pu must each contain {generator_count} values")
    if not np.isfinite(pg).all() or not np.isfinite(vg).all():
        raise ValueError("candidate output contains non-finite values")

    gen = mpc["gen"]
    online = gen[:, GEN_STATUS] > 0
    if np.any(pg[online] < gen[online, PMIN] - 1e-6) or np.any(pg[online] > gen[online, PMAX] + 1e-6):
        raise ValueError("candidate active power is outside generator limits")

    bus_limits = {row["bus_id"]: (row["vmin_pu"], row["vmax_pu"]) for row in payload["buses"]}
    voltage_by_bus: dict[int, float] = {}
    for index, row in enumerate(gen):
        if not online[index]:
            continue
        bus_id = int(row[GEN_BUS])
        low, high = bus_limits[bus_id]
        if vg[index] < low - 1e-8 or vg[index] > high + 1e-8:
            raise ValueError(f"generator voltage at bus {bus_id} is outside bus limits")
        if bus_id in voltage_by_bus and abs(voltage_by_bus[bus_id] - vg[index]) > 1e-7:
            raise ValueError(f"generators at bus {bus_id} must use the same voltage setpoint")
        voltage_by_bus[bus_id] = float(vg[index])
    return pg, vg


def evaluate(candidate_path: Path) -> tuple[dict[str, float], dict[str, Any]]:
    start = time.time()
    scenario_data = json.loads((TASK_ROOT / "references" / "scenarios.json").read_text(encoding="utf-8"))
    case_cache: dict[str, dict[str, Any]] = {}
    details = []
    scenario_scores = []
    feasible_count = 0
    first_error = ""
    expected_scenarios = len(scenario_data["scenarios"])

    for scenario in scenario_data["scenarios"]:
        case_id = scenario["case_id"]
        if case_id not in case_cache:
            case_cache[case_id] = load_case(TASK_ROOT / "references" / "pglib" / scenario["source_file"])
        mpc = apply_scenario(
            case_cache[case_id],
            load_scale=float(scenario["load_scale"]),
            outage_branch=scenario["outage_branch"],
        )
        payload = public_payload(mpc, scenario)
        record: dict[str, Any] = {
            "case_id": case_id,
            "scenario_id": scenario["scenario_id"],
            "valid": False,
            "score": 0.0,
        }
        timed_out = False
        try:
            output = run_candidate(candidate_path, payload)
            pg, vg = parse_output(output, mpc, payload)
            repeated_output = run_candidate(candidate_path, payload)
            repeated_pg, repeated_vg = parse_output(repeated_output, mpc, payload)
            if not np.array_equal(pg, repeated_pg) or not np.array_equal(vg, repeated_vg):
                raise ValueError("candidate solve(case) must be deterministic")
            result = run_candidate_pf(mpc, pg, vg)
            valid, checks = assess_result(result)
            record.update(checks)
            if not valid:
                raise ValueError("AC power flow violates one or more hard constraints")
            cost = generation_cost(result)
            if not math.isfinite(cost) or cost <= 0:
                raise ValueError("candidate generation cost is invalid")
            cost_efficiency = min(1.05, float(scenario["reference_cost"]) / cost)
            thermal_margin = float(
                np.clip((100.0 - checks["max_loading_percent"]) / 20.0, 0.0, 1.0)
            )
            bus = result["bus"]
            voltage_band = np.maximum(bus[:, VMAX] - bus[:, VMIN], 1e-9)
            normalized_voltage_margin = (
                2.0
                * np.minimum(bus[:, VM] - bus[:, VMIN], bus[:, VMAX] - bus[:, VM])
                / voltage_band
            )
            voltage_margin = float(
                np.clip(np.percentile(normalized_voltage_margin, 10.0), 0.0, 1.0)
            )
            score = 70.0 * cost_efficiency + 20.0 * thermal_margin + 10.0 * voltage_margin
            record.update(
                {
                    "valid": True,
                    "cost": cost,
                    "cost_efficiency": cost_efficiency,
                    "thermal_margin_score": thermal_margin,
                    "voltage_margin_score": voltage_margin,
                    "score": score,
                }
            )
            feasible_count += 1
            scenario_scores.append(score)
        except Exception as exc:
            timed_out = "exceeded" in str(exc).lower()
            record["error"] = f"{type(exc).__name__}: {exc}"
            if not first_error:
                first_error = f"{case_id}/{scenario['scenario_id']}: {record['error']}"
        details.append(record)
        if timed_out:
            break

    total = expected_scenarios
    feasible_fraction = feasible_count / total if total else 0.0
    all_valid = feasible_count == total and total > 0
    mean_score = float(np.mean(scenario_scores)) if scenario_scores else 0.0
    min_score = float(np.min(scenario_scores)) if scenario_scores else 0.0
    combined_score = 0.75 * mean_score + 0.25 * min_score if all_valid else 0.0
    metrics = {
        "valid": 1.0 if all_valid else 0.0,
        "combined_score": combined_score,
        "mean_scenario_score": mean_score,
        "worst_scenario_score": min_score,
        "feasible_fraction": feasible_fraction,
        "scenarios_feasible": float(feasible_count),
        "scenarios_total": float(total),
        "runtime_s": float(time.time() - start),
    }
    artifacts = {
        "candidate_path": str(candidate_path),
        "pglib_release": scenario_data["pglib_release"],
        "pglib_commit": scenario_data["pglib_commit"],
        "failure_summary": first_error,
        "scenario_results": details,
    }
    return metrics, artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a PGLib security-constrained dispatch policy.")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--metrics-out", type=Path, default=Path("metrics.json"))
    parser.add_argument("--artifacts-out", type=Path, default=Path("artifacts.json"))
    args = parser.parse_args()

    try:
        metrics, artifacts = evaluate(args.candidate.resolve())
    except Exception as exc:
        metrics = {
            "valid": 0.0,
            "combined_score": 0.0,
            "feasible_fraction": 0.0,
            "runtime_s": 0.0,
        }
        artifacts = {"failure_summary": f"evaluator failure: {type(exc).__name__}: {exc}"}
    write_json(args.metrics_out.resolve(), metrics)
    write_json(args.artifacts_out.resolve(), artifacts)
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
