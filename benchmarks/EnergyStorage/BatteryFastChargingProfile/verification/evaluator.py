#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

TASK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = TASK_ROOT / "references" / "battery_config.json"

# Wall-clock budget for the candidate's own process. The profile builder is a
# pure function of the published config, so this is generous by design.
CANDIDATE_TIMEOUT_S = 300.0

def _find_repo_root() -> Path:
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    raise RuntimeError("could not locate repo root for BatteryFastChargingProfile evaluator")


# Import the isolation helper at *module import time*, i.e. strictly before the
# candidate has ever run. It lives outside every benchmark directory so a
# copy_files.txt of "." cannot drag it into the sandbox for the candidate to
# rewrite.
_SHARED_DIR = str(_find_repo_root() / "benchmarks" / "_shared")
if _SHARED_DIR not in sys.path:
    sys.path.insert(0, _SHARED_DIR)
import candidate_sandbox as sandbox  # noqa: E402


# Runner executed inside the sandbox subprocess. It imports the candidate,
# calls the entry point and serialises the *data* it returned. Anything that is
# not JSON (a callable, an object, a patched module) fails here, in the child,
# where it cannot touch this scorer.
_RUNNER_SOURCE = '''#!/usr/bin/env python3
"""Sandbox runner for BatteryFastChargingProfile candidates."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    # Never drop a __pycache__ next to the candidate: the scoring path must not
    # write into the task tree it is grading.
    sys.dont_write_bytecode = True
    candidate_path = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(candidate_path.parent))
    spec = importlib.util.spec_from_file_location("battery_fast_charge_candidate", candidate_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load candidate module from %s" % candidate_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except SystemExit as exc:
        # Refuse to let import-time sys.exit() short-circuit the runner and
        # leave whatever the candidate may have dropped on disk standing in
        # for a real return value.
        raise RuntimeError("candidate called sys.exit() during import") from exc
    if not hasattr(module, "build_charging_profile"):
        raise AttributeError("candidate must define build_charging_profile()")
    fn = getattr(module, "build_charging_profile")
    if not callable(fn):
        raise TypeError("build_charging_profile must be callable")
    profile = fn()
    Path("submission.json").write_text(json.dumps(profile), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _load_config(config_path: Path) -> dict[str, Any]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("battery config must be a JSON object")
    return data


def _ocv_from_soc(soc: float, cfg: dict[str, Any]) -> float:
    model = cfg["electrical_model"]
    z = _clamp(soc, 0.0, 1.0)
    return (
        float(model["ocv_base_v"])
        + float(model["ocv_linear_v_per_soc"]) * z
        + float(model["ocv_tanh_1_amplitude_v"])
        * math.tanh((z - float(model["ocv_tanh_1_center_soc"])) * float(model["ocv_tanh_1_gain"]))
        + float(model["ocv_tanh_2_amplitude_v"])
        * math.tanh((z - float(model["ocv_tanh_2_center_soc"])) * float(model["ocv_tanh_2_gain"]))
    )


def _internal_resistance_ohm(soc: float, temp_c: float, cfg: dict[str, Any]) -> float:
    model = cfg["electrical_model"]
    battery = cfg["battery"]
    soc_term = (
        float(model["r0_base_ohm"])
        + float(model["r0_high_soc_gain_ohm"]) * max(0.0, soc - float(model["r0_high_soc_center"])) ** 2
        + float(model["r0_low_soc_gain_ohm"]) * max(0.0, float(model["r0_low_soc_center"]) - soc) ** 2
    )
    temp_term = float(model["r0_temp_gain_ohm_per_c"]) * max(0.0, float(battery["ambient_temp_c"]) - temp_c)
    return soc_term + temp_term


def _load_candidate(path: Path) -> Any:
    """Run the candidate in its own process and return only the JSON it wrote.

    The candidate never executes inside this interpreter, so it cannot reach
    ``_validate_profile`` / ``_simulate`` -- where every hard limit (4.25 V,
    47 C, 2400 s) is enforced -- to replace them.
    """
    candidate_path = Path(path).resolve()
    with tempfile.TemporaryDirectory(prefix="fe_profile_runner_") as tmp:
        runner_path = Path(tmp) / "_profile_candidate_runner.py"
        runner_path.write_text(_RUNNER_SOURCE, encoding="utf-8")
        try:
            run = sandbox.run_candidate_isolated(
                runner_path,
                expected_outputs=("submission.json",),
                timeout_s=CANDIDATE_TIMEOUT_S,
                argv=(str(candidate_path),),
                copy_into_workdir=True,
            )
        except sandbox.InvalidSubmissionError as exc:
            raise RuntimeError(f"candidate produced no usable submission: {exc}") from exc

    if run.timed_out:
        raise RuntimeError(f"candidate exceeded the {CANDIDATE_TIMEOUT_S:.0f}s time budget")
    if run.returncode != 0:
        detail = (run.stderr_tail or "").strip().splitlines()
        tail = detail[-1] if detail else "no stderr"
        raise RuntimeError(f"candidate exited non-zero ({run.returncode}): {tail}")

    return sandbox.load_json_output(run)


def _finite_number(value: Any, label: str) -> float:
    """Accept only a real, finite number.

    ``isinstance(x, (int, float))`` alone lets ``True``, ``float("inf")`` and
    ``float("nan")`` through, and every interval test below is *false* for NaN,
    so a NaN would silently take whichever branch happens to be safe-looking.
    Reject all three explicitly instead. JSON round-trips ``Infinity``/``NaN``
    literals, so this must be checked after parsing, not only before.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number, got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return number


def _validate_profile(profile: Any, cfg: dict[str, Any]) -> tuple[list[float], list[float]]:
    if not isinstance(profile, dict):
        raise TypeError("build_charging_profile() must return a dict")

    currents = profile.get("currents_c")
    switch_soc = profile.get("switch_soc", [])

    if not isinstance(currents, list):
        raise TypeError("currents_c must be a list of numbers")
    if not isinstance(switch_soc, list):
        raise TypeError("switch_soc must be a list of numbers")
    bounds = cfg["profile_bounds"]

    if not (int(bounds["min_stages"]) <= len(currents) <= int(bounds["max_stages"])):
        raise ValueError("currents_c stage count is outside configured bounds")
    if len(switch_soc) != len(currents) - 1:
        raise ValueError("switch_soc length must equal len(currents_c) - 1")

    currents_f = [_finite_number(x, f"currents_c[{i}]") for i, x in enumerate(currents)]
    switch_f = [_finite_number(x, f"switch_soc[{i}]") for i, x in enumerate(switch_soc)]

    for current in currents_f:
        if not (float(bounds["min_current_c"]) <= current <= float(bounds["max_current_c"])):
            raise ValueError("each current must be within configured current bounds")

    target_soc = float(cfg["battery"]["target_soc"])
    last = float(cfg["battery"]["initial_soc"])
    for threshold in switch_f:
        if not (float(bounds["min_switch_soc"]) < threshold < target_soc):
            raise ValueError("each switch_soc threshold must lie within configured SOC bounds")
        if threshold <= last:
            raise ValueError("switch_soc must be strictly increasing")
        last = threshold

    return currents_f, switch_f


def _simulate(currents_c: list[float], switch_soc: list[float], cfg: dict[str, Any]) -> dict[str, Any]:
    battery = cfg["battery"]
    limits = cfg["limits"]
    sim = cfg["simulation"]
    polar = cfg["polarization_model"]
    plating = cfg["plating_model"]
    thermal = cfg["thermal_model"]
    aging = cfg["aging_model"]
    eff = cfg["efficiency_model"]
    scoring = cfg["scoring"]

    capacity_ah = float(battery["capacity_ah"])
    initial_soc = float(battery["initial_soc"])
    target_soc = float(battery["target_soc"])
    ambient_temp_c = float(battery["ambient_temp_c"])
    dt_s = float(sim["dt_s"])
    max_time_s = float(sim["max_time_s"])

    soc = initial_soc
    temp_c = ambient_temp_c
    eta_pol_v = 0.0
    eta_diff_v = 0.0
    plating_loss_ah = 0.0
    aging_loss_ah = 0.0
    throughput_ah = 0.0
    max_temp_c = temp_c
    max_voltage_v = 0.0

    time_s = 0.0
    stage_idx = 0
    stage_endpoints = list(switch_soc) + [target_soc]

    while time_s < max_time_s and soc < target_soc:
        while stage_idx < len(stage_endpoints) - 1 and soc >= stage_endpoints[stage_idx]:
            stage_idx += 1

        current_c = currents_c[stage_idx]
        current_a = current_c * capacity_ah

        r0 = _internal_resistance_ohm(soc, temp_c, cfg)
        tau_pol_s = float(polar["tau_pol_s"])
        tau_diff_s = float(polar["tau_diff_s"])
        eta_pol_target = current_a * (
            float(polar["eta_pol_base_coeff"])
            + float(polar["eta_pol_high_soc_coeff"]) * max(0.0, soc - float(polar["eta_pol_high_soc_center"]))
        )
        eta_diff_target = current_a * (
            float(polar["eta_diff_base_coeff"])
            + float(polar["eta_diff_high_soc_coeff"]) * max(0.0, soc - float(polar["eta_diff_high_soc_center"]))
        )
        eta_pol_v += (eta_pol_target - eta_pol_v) * (dt_s / tau_pol_s)
        eta_diff_v += (eta_diff_target - eta_diff_v) * (dt_s / tau_diff_s)

        voltage_v = _ocv_from_soc(soc, cfg) + current_a * r0 + eta_pol_v + eta_diff_v
        max_voltage_v = max(max_voltage_v, voltage_v)
        if voltage_v > float(limits["hard_voltage_cutoff_v"]):
            return {
                "valid": 0.0,
                "failure_reason": "voltage_cutoff",
                "charge_time_s": time_s,
                "max_temp_c": max_temp_c,
                "max_voltage_v": max_voltage_v,
                "plating_loss_ah": plating_loss_ah,
                "aging_loss_ah": aging_loss_ah,
                "throughput_ah": throughput_ah,
                "combined_score": 0.0,
            }

        anode_margin_v = (
            float(plating["base_margin_v"])
            + float(plating["soc_margin_coeff_v"]) * (1.0 - soc)
            - float(plating["current_coeff_v_per_c"]) * current_c
            - float(plating["diff_coeff_v_per_v"]) * eta_diff_v
            - float(plating["cold_coeff_v_per_c"]) * max(0.0, ambient_temp_c - temp_c)
        )
        plating_drive = max(0.0, -anode_margin_v)
        plating_loss_ah += float(plating["plating_loss_coeff"]) * current_a * plating_drive * (dt_s / 3600.0)

        aging_rate = (
            float(aging["aging_base_rate"])
            * (1.0 + float(aging["aging_current_coeff"]) * current_c ** float(aging["aging_current_exp"]))
            * math.exp(float(aging["aging_temp_exp_coeff"]) * max(0.0, temp_c - ambient_temp_c))
        )
        aging_loss_ah += aging_rate * (dt_s / 3600.0) + float(aging["plating_to_aging_coeff"]) * plating_loss_ah * (dt_s / max_time_s)

        heat_w = current_a * current_a * r0 + float(thermal["heat_pol_coeff"]) * current_a * abs(eta_pol_v + eta_diff_v)
        heat_capacity_j_per_k = float(thermal["heat_capacity_j_per_k"])
        cooling_w_per_k = float(thermal["cooling_w_per_k"])
        temp_c += dt_s * (heat_w - cooling_w_per_k * (temp_c - ambient_temp_c)) / heat_capacity_j_per_k
        max_temp_c = max(max_temp_c, temp_c)
        if temp_c > float(limits["hard_temp_c"]):
            return {
                "valid": 0.0,
                "failure_reason": "thermal_cutoff",
                "charge_time_s": time_s,
                "max_temp_c": max_temp_c,
                "max_voltage_v": max_voltage_v,
                "plating_loss_ah": plating_loss_ah,
                "aging_loss_ah": aging_loss_ah,
                "throughput_ah": throughput_ah,
                "combined_score": 0.0,
            }

        coulombic_eff = max(float(eff["min_efficiency"]), float(eff["base_efficiency"]) - float(eff["plating_efficiency_penalty"]) * plating_drive)
        delta_ah = current_a * coulombic_eff * (dt_s / 3600.0)
        soc += delta_ah / capacity_ah
        throughput_ah += current_a * (dt_s / 3600.0)
        time_s += dt_s

    if soc < target_soc:
        return {
            "valid": 0.0,
            "failure_reason": "timeout",
            "charge_time_s": time_s,
            "max_temp_c": max_temp_c,
            "max_voltage_v": max_voltage_v,
            "plating_loss_ah": plating_loss_ah,
            "aging_loss_ah": aging_loss_ah,
            "throughput_ah": throughput_ah,
            "combined_score": 0.0,
        }

    time_score = math.exp(-(time_s - float(scoring["time_reference_s"])) / float(scoring["time_scale_s"]))
    degradation_score = math.exp(
        -float(scoring["degradation_plating_coeff"]) * plating_loss_ah
        - float(scoring["degradation_aging_coeff"]) * aging_loss_ah
    )
    thermal_score = math.exp(
        -max(0.0, max_temp_c - float(scoring["thermal_reference_c"])) / float(scoring["thermal_scale_c"])
    )
    voltage_score = math.exp(
        -max(0.0, max_voltage_v - float(limits["max_voltage_v"])) / float(scoring["voltage_scale_v"])
    )
    combined_score = float(scoring["score_scale"]) * (
        float(scoring["weight_time"]) * time_score
        + float(scoring["weight_degradation"]) * degradation_score
        + float(scoring["weight_thermal"]) * thermal_score
        + float(scoring["weight_voltage"]) * voltage_score
    )

    return {
        "valid": 1.0,
        "failure_reason": "",
        "charge_time_s": time_s,
        "max_temp_c": max_temp_c,
        "max_voltage_v": max_voltage_v,
        "plating_loss_ah": plating_loss_ah,
        "aging_loss_ah": aging_loss_ah,
        "throughput_ah": throughput_ah,
        "time_score": time_score,
        "degradation_score": degradation_score,
        "thermal_score": thermal_score,
        "voltage_score": voltage_score,
        "combined_score": combined_score,
        "soft_temp_violation": 1.0 if max_temp_c > float(limits["soft_temp_c"]) else 0.0,
        "soft_voltage_violation": 1.0 if max_voltage_v > float(limits["max_voltage_v"]) else 0.0,
    }


def evaluate(candidate_path: Path, config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    try:
        cfg = _load_config(config_path)
        profile = _load_candidate(candidate_path)
        currents_c, switch_soc = _validate_profile(profile, cfg)
        result = _simulate(currents_c, switch_soc, cfg)
        result["currents_c"] = currents_c
        result["switch_soc"] = switch_soc
        result["config_path"] = str(config_path.resolve())
        result["battery_name"] = str(cfg["battery"].get("name", "battery"))
        return result
    except Exception as exc:
        return {
            "valid": 0.0,
            "combined_score": 0.0,
            "failure_reason": f"exception: {exc}",
            "traceback": traceback.format_exc(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a battery fast-charging candidate.")
    parser.add_argument("candidate", help="Path to candidate Python file")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to battery parameter JSON")
    parser.add_argument("--json-out", default=None, help="Optional path to metrics JSON")
    parser.add_argument("--artifacts-out", default=None, help="Optional path to artifacts JSON")
    args = parser.parse_args()

    candidate_path = Path(args.candidate).resolve()
    config_path = Path(args.config).resolve()
    result = evaluate(candidate_path, config_path=config_path)

    metrics = dict(result)
    metrics["candidate_path"] = str(candidate_path)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(metrics, indent=2, ensure_ascii=True), encoding="utf-8")

    if args.artifacts_out:
        artifacts = {
            "candidate_path": str(candidate_path),
            "config_path": str(config_path),
            "failure_reason": result.get("failure_reason", ""),
            "currents_c": result.get("currents_c", []),
            "switch_soc": result.get("switch_soc", []),
        }
        if "traceback" in result:
            artifacts["traceback"] = result["traceback"]
        Path(args.artifacts_out).write_text(json.dumps(artifacts, indent=2, ensure_ascii=True), encoding="utf-8")

    print(json.dumps(metrics, ensure_ascii=True))


if __name__ == "__main__":
    main()
