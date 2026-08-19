"""Evaluator for the BSM1AerationControl benchmark."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

try:
    from .bsm1_model import (
        BSM1Plant, SNH, SNO, SO, action_energy, advanced_quantities,
        effluent_quality_index, influent_at, load_config,
    )
    from .policy_runtime import PolicyRuntime
except ImportError:
    from bsm1_model import (
        BSM1Plant, SNH, SNO, SO, action_energy, advanced_quantities,
        effluent_quality_index, influent_at, load_config,
    )
    from policy_runtime import PolicyRuntime


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "scripts" / "init.py"
ACTION_KEYS = (
    "kla3_per_day", "kla4_per_day", "kla5_per_day", "internal_recycle_m3_per_day",
)


def validate_action(value: Any, previous: Mapping[str, float], config: Mapping[str, Any]) -> dict[str, float]:
    if not isinstance(value, dict):
        raise TypeError("control must return a JSON object")
    if set(value) != set(ACTION_KEYS):
        missing = sorted(set(ACTION_KEYS) - set(value))
        extra = sorted(set(value) - set(ACTION_KEYS))
        raise ValueError(f"action keys mismatch; missing={missing}, extra={extra}")
    action: dict[str, float] = {}
    for key in ACTION_KEYS:
        raw = value[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError(f"action[{key!r}] must be a finite number")
        number = float(raw)
        if not math.isfinite(number):
            raise ValueError(f"action[{key!r}] must be finite")
        action[key] = number

    limits = config["action"]
    for key in ACTION_KEYS[:3]:
        if not limits["kla_min_per_day"] <= action[key] <= limits["kla_max_per_day"]:
            raise ValueError(f"action[{key!r}] is outside the KLa range")
        if abs(action[key] - previous[key]) > limits["kla_max_change_per_step"] + 1e-9:
            raise ValueError(f"action[{key!r}] exceeds the per-step KLa slew limit")
    recycle_key = "internal_recycle_m3_per_day"
    if not limits["qintr_min_m3_per_day"] <= action[recycle_key] <= limits["qintr_max_m3_per_day"]:
        raise ValueError("internal recycle flow is outside its range")
    if abs(action[recycle_key] - previous[recycle_key]) > limits["qintr_max_change_per_step"] + 1e-9:
        raise ValueError("internal recycle flow exceeds its per-step slew limit")
    return action


def _observation(
    plant: BSM1Plant,
    scenario: Mapping[str, str],
    time_day: float,
    influent: np.ndarray,
    previous: Mapping[str, float],
    noise: Mapping[str, float],
    step_minutes: float,
) -> dict[str, Any]:
    advanced = advanced_quantities(plant.effluent)
    return {
        "scenario_id": scenario["scenario_id"],
        "weather": scenario["weather"],
        "time_day": float(time_day),
        "step_minutes": float(step_minutes),
        "influent_flow_m3_per_day": float(influent[14]),
        "influent_ammonium_gN_per_m3": float(influent[SNH]),
        "reactor3_do_gO2_per_m3": max(0.0, float(plant.reactors[2, SO]) + noise["do3"]),
        "reactor4_do_gO2_per_m3": max(0.0, float(plant.reactors[3, SO]) + noise["do4"]),
        "reactor5_do_gO2_per_m3": max(0.0, float(plant.reactors[4, SO]) + noise["do5"]),
        "reactor2_nitrate_gN_per_m3": max(0.0, float(plant.reactors[1, SNO]) + noise["nitrate"]),
        "effluent_ammonium_gN_per_m3": max(0.0, float(plant.effluent[SNH]) + noise["ammonium"]),
        "effluent_total_nitrogen_gN_per_m3": float(advanced["total_nitrogen"]),
        "previous_action": dict(previous),
    }


def _score(metrics: Mapping[str, float], config: Mapping[str, Any]) -> float:
    scoring = config["scoring"]
    quality = math.exp(
        -metrics["eqi_kg_pollution_units_per_day"] / scoring["eqi_scale"]
    )
    aeration = math.exp(
        -metrics["aeration_energy_kwh_per_day"] / scoring["aeration_energy_scale"]
    )
    pumping = math.exp(
        -metrics["pumping_energy_kwh_per_day"] / scoring["pumping_energy_scale"]
    )
    mixing = math.exp(
        -metrics["mixing_energy_kwh_per_day"] / scoring["mixing_energy_scale"]
    )
    smoothness = math.exp(-scoring["switching_exponent"] * metrics["switching_index"])
    weights = scoring["objective_weights"]
    base = 100.0 * (
        weights["quality"] * quality
        + weights["aeration"] * aeration
        + weights["pumping"] * pumping
        + weights["mixing"] * mixing
        + weights["smoothness"] * smoothness
    )
    compliance = math.exp(
        -scoring["violation_exponent"] * metrics["violation_index"]
    )
    return float(np.clip(base * compliance, 0.0, 100.0))


def simulate_scenario(
    scenario: Mapping[str, str],
    action_provider: Callable[[dict[str, Any]], Any],
    reset_provider: Callable[[dict[str, Any]], None],
    *,
    max_steps: int | None = None,
) -> dict[str, Any]:
    config = load_config()
    simulation = config["simulation"]
    step_minutes = float(simulation["step_minutes"])
    dt_days = step_minutes / (24.0 * 60.0)
    total_steps = int(round(float(simulation["days"]) / dt_days))
    if max_steps is not None:
        total_steps = min(total_steps, int(max_steps))
    evaluation_start = float(simulation["evaluation_start_day"])
    if max_steps is not None and total_steps * dt_days <= evaluation_start:
        evaluation_start = 0.0

    descriptor = {
        "scenario_id": scenario["scenario_id"], "weather": scenario["weather"],
        "duration_days": total_steps * dt_days, "step_minutes": step_minutes,
    }
    reset_provider(descriptor)
    plant = BSM1Plant()
    previous = {key: float(config["reference_action"][key]) for key in ACTION_KEYS}
    seed_offset = {"dry": 0, "rain": 1000, "storm": 2000}[scenario["weather"]]
    rng = np.random.default_rng(int(simulation["sensor_noise_seed"]) + seed_offset)
    std = simulation["sensor_noise_std"]

    eqi_values: list[float] = []
    aeration_values: list[float] = []
    pumping_values: list[float] = []
    mixing_values: list[float] = []
    switching_values: list[float] = []
    violation_values: list[float] = []
    violation_excess: dict[str, list[float]] = {
        name: [] for name in ("ammonium", "total_nitrogen", "cod", "tss", "bod5")
    }
    maximum_quantities = {name: 0.0 for name in violation_excess}
    effluent_rows: list[dict[str, float]] = []

    for index in range(total_steps):
        time_day = index * dt_days
        influent = influent_at(time_day, scenario["weather"])
        noise = {
            "do3": rng.normal(0.0, std["dissolved_oxygen"]),
            "do4": rng.normal(0.0, std["dissolved_oxygen"]),
            "do5": rng.normal(0.0, std["dissolved_oxygen"]),
            "nitrate": rng.normal(0.0, std["nitrate"]),
            "ammonium": rng.normal(0.0, std["ammonium"]),
        }
        observation = _observation(plant, scenario, time_day, influent, previous, noise, step_minutes)
        action = validate_action(action_provider(observation), previous, config)
        effluent = plant.step(influent, action, dt_days)
        if time_day >= evaluation_start:
            advanced = advanced_quantities(effluent)
            energy = action_energy(action)
            limits = config["limits"]
            quantities = {
                "ammonium": float(effluent[SNH]),
                "total_nitrogen": advanced["total_nitrogen"],
                "cod": advanced["cod"], "tss": advanced["tss"], "bod5": advanced["bod5"],
            }
            limit_keys = {
                "ammonium": "ammonium_gN_per_m3",
                "total_nitrogen": "total_nitrogen_gN_per_m3",
                "cod": "cod_gCOD_per_m3",
                "tss": "tss_gSS_per_m3",
                "bod5": "bod5_gBOD_per_m3",
            }
            normalized_excess = [
                max(0.0, quantities[name] / limits[limit_key] - 1.0)
                for name, limit_key in limit_keys.items()
            ]
            for name, excess in zip(limit_keys, normalized_excess):
                violation_excess[name].append(float(excess))
                maximum_quantities[name] = max(
                    maximum_quantities[name], float(quantities[name])
                )
            switching = sum(
                abs(action[key] - previous[key]) / (360.0 if key.startswith("kla") else 92230.0)
                for key in ACTION_KEYS
            )
            eqi_values.append(effluent_quality_index(effluent))
            aeration_values.append(energy["aeration"])
            pumping_values.append(energy["pumping"])
            mixing_values.append(energy["mixing"])
            switching_values.append(float(switching))
            violation_values.append(float(np.mean(normalized_excess)))
            samples_per_day = max(1, int(round(24.0 * 60.0 / step_minutes)))
            if index % samples_per_day == 0 or index == total_steps - 1:
                effluent_rows.append({"time_day": time_day, **quantities})
        previous = action

    if not eqi_values:
        raise ValueError("scenario has no evaluation samples")
    metrics = {
        "eqi_kg_pollution_units_per_day": float(np.mean(eqi_values)),
        "aeration_energy_kwh_per_day": float(np.mean(aeration_values)),
        "pumping_energy_kwh_per_day": float(np.mean(pumping_values)),
        "mixing_energy_kwh_per_day": float(np.mean(mixing_values)),
        "switching_index": float(np.mean(switching_values)),
        "violation_index": float(np.mean(violation_values)),
        "max_ammonium_gN_per_m3": maximum_quantities["ammonium"],
        "max_total_nitrogen_gN_per_m3": maximum_quantities["total_nitrogen"],
        "max_cod_gCOD_per_m3": maximum_quantities["cod"],
        "max_tss_gSS_per_m3": maximum_quantities["tss"],
        "max_bod5_gBOD_per_m3": maximum_quantities["bod5"],
    }
    for name, values in violation_excess.items():
        metrics[f"{name}_violation_fraction"] = float(np.mean(np.asarray(values) > 0.0))
        metrics[f"{name}_mean_normalized_excess"] = float(np.mean(values))
    return {
        "scenario_id": scenario["scenario_id"], "weather": scenario["weather"],
        "score": _score(metrics, config), "metrics": metrics, "effluent_samples": effluent_rows,
    }


def evaluate(candidate_path: Path, *, max_steps: int | None = None) -> dict[str, Any]:
    config = load_config()
    rows: list[dict[str, Any]] = []
    try:
        with PolicyRuntime(candidate_path) as runtime:
            for scenario in config["scenarios"]:
                rows.append(simulate_scenario(
                    scenario, runtime.control, runtime.reset, max_steps=max_steps,
                ))
    except Exception as exc:
        return {
            "combined_score": 0.0, "diagnostic_score": 0.0, "valid": 0.0,
            "completed_scenarios": float(len(rows)), "error": f"{type(exc).__name__}: {exc}",
            "rows": rows,
        }
    scores = np.asarray([row["score"] for row in rows], dtype=float)
    scoring = config["scoring"]
    diagnostic = float(
        scoring["mean_weight"] * np.mean(scores)
        + scoring["worst_case_weight"] * np.min(scores)
    )
    return {
        "combined_score": diagnostic, "diagnostic_score": diagnostic, "valid": 1.0,
        "completed_scenarios": float(len(rows)), "rows": rows,
    }


def _write_json(path: str | None, payload: Mapping[str, Any]) -> None:
    if not path:
        return
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a BSM1 aeration controller")
    parser.add_argument("candidate", nargs="?", default=str(DEFAULT_CANDIDATE))
    parser.add_argument("--metrics-out", default=None)
    parser.add_argument("--artifacts-out", default=None)
    args = parser.parse_args()
    candidate = Path(args.candidate).expanduser().resolve()
    result = evaluate(candidate)
    print("=== BSM1 Aeration Control ===")
    for row in result["rows"]:
        metrics = row["metrics"]
        print(
            f"scenario={row['scenario_id']} score={row['score']:.3f} "
            f"eqi={metrics['eqi_kg_pollution_units_per_day']:.2f} "
            f"ae={metrics['aeration_energy_kwh_per_day']:.2f} "
            f"violations={metrics['violation_index']:.6f}"
        )
    if "error" in result:
        print(f"error: {result['error']}")
    print("---")
    print(f"completed_scenarios: {result['completed_scenarios']:.0f}/{len(load_config()['scenarios'])}")
    print(f"diagnostic_score: {result['diagnostic_score']:.4f}")
    print(f"combined_score: {result['combined_score']:.4f}")
    metrics_out = {
        "combined_score": float(result["combined_score"]),
        "diagnostic_score": float(result["diagnostic_score"]),
        "valid": float(result["valid"]),
        "completed_scenarios": float(result["completed_scenarios"]),
        "num_scenarios": float(len(load_config()["scenarios"])),
    }
    _write_json(args.metrics_out, metrics_out)
    _write_json(args.artifacts_out, {"candidate_path": candidate.name, "rows": result["rows"]})


if __name__ == "__main__":
    main()
