from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
import time
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any


INVALID_COMBINED_SCORE = -1e18


def _write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_candidate(candidate_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("microgrid_candidate", candidate_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load candidate module from {candidate_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _case_profiles(case_id: str, hours: int, scale: float, pv_scale: float, phase: float) -> dict[str, Any]:
    load: list[float] = []
    pv: list[float] = []
    buy: list[float] = []
    sell: list[float] = []
    for t in range(hours):
        hour = t % 24
        weekday = (t // 24) % 7
        morning = math.exp(-((hour - 8.0) / 3.0) ** 2)
        evening = math.exp(-((hour - 18.0) / 4.0) ** 2)
        base = scale * (86.0 + 16.0 * morning + 34.0 * evening)
        weather = 1.0 + 0.08 * math.sin(0.47 * t + phase) + 0.04 * math.cos(0.19 * t)
        load.append(max(25.0, base * weather + (6.0 if weekday >= 5 else 0.0)))

        sun = max(0.0, math.sin(math.pi * (hour - 6.0) / 12.0))
        cloud = 0.72 + 0.20 * math.sin(0.31 * t + phase) + 0.08 * math.cos(0.11 * t + 1.7)
        pv.append(max(0.0, pv_scale * 92.0 * sun * max(0.15, cloud)))

        peak = 1.0 if 16 <= hour <= 21 else 0.0
        shoulder = 1.0 if 7 <= hour <= 15 else 0.0
        night = 1.0 if hour <= 5 or hour >= 22 else 0.0
        buy_price = 0.105 + 0.175 * peak + 0.055 * shoulder - 0.018 * night
        buy_price += 0.012 * math.sin(0.23 * t + phase)
        buy.append(max(0.05, buy_price))
        sell.append(max(0.025, 0.42 * buy[-1] - 0.015))

    return {
        "case_id": case_id,
        "load_kw": load,
        "pv_kw": pv,
        "buy_price": buy,
        "sell_price": sell,
    }


def _build_cases() -> list[dict[str, Any]]:
    cases = [
        _case_profiles("office_summer_peak", 96, 1.05, 1.05, 0.2),
        _case_profiles("hospital_cloudy_week", 120, 1.28, 0.62, 1.4),
        _case_profiles("warehouse_solar_rich", 96, 0.82, 1.38, 2.6),
    ]
    params = [
        {
            "capacity_kwh": 260.0,
            "initial_soc_kwh": 132.0,
            "min_soc_kwh": 31.0,
            "max_charge_kw": 70.0,
            "max_discharge_kw": 72.0,
            "charge_efficiency": 0.94,
            "discharge_efficiency": 0.93,
            "demand_charge_per_kw": 15.5,
            "degradation_cost_per_kwh": 0.018,
        },
        {
            "capacity_kwh": 420.0,
            "initial_soc_kwh": 250.0,
            "min_soc_kwh": 84.0,
            "max_charge_kw": 95.0,
            "max_discharge_kw": 92.0,
            "charge_efficiency": 0.93,
            "discharge_efficiency": 0.92,
            "demand_charge_per_kw": 18.0,
            "degradation_cost_per_kwh": 0.022,
        },
        {
            "capacity_kwh": 190.0,
            "initial_soc_kwh": 78.0,
            "min_soc_kwh": 23.0,
            "max_charge_kw": 54.0,
            "max_discharge_kw": 58.0,
            "charge_efficiency": 0.95,
            "discharge_efficiency": 0.94,
            "demand_charge_per_kw": 12.5,
            "degradation_cost_per_kwh": 0.016,
        },
    ]
    for case, extra in zip(cases, params, strict=True):
        case.update(extra)
    return cases


def _forecast(values: list[float], t: int, horizon: int = 24) -> list[float]:
    if not values:
        return []
    return [float(values[min(len(values) - 1, t + k)]) for k in range(horizon)]


def _simulate_case(dispatch_action: Any, case: dict[str, Any]) -> dict[str, Any]:
    soc = float(case["initial_soc_kwh"])
    capacity = float(case["capacity_kwh"])
    min_soc = float(case["min_soc_kwh"])
    charge_eff = float(case["charge_efficiency"])
    discharge_eff = float(case["discharge_efficiency"])
    max_charge = float(case["max_charge_kw"])
    max_discharge = float(case["max_discharge_kw"])

    import_cost = 0.0
    export_credit = 0.0
    degradation_cost = 0.0
    infeasible_penalty = 0.0
    peak_import_kw = 0.0
    throughput_kwh = 0.0
    actions: list[float] = []
    soc_trace: list[float] = [soc]

    hours = len(case["load_kw"])
    for t in range(hours):
        state = {
            "case_id": case["case_id"],
            "t": t,
            "hour": t % 24,
            "soc_kwh": soc,
            "min_soc_kwh": min_soc,
            "capacity_kwh": capacity,
            "max_charge_kw": max_charge,
            "max_discharge_kw": max_discharge,
            "charge_efficiency": charge_eff,
            "discharge_efficiency": discharge_eff,
            "demand_charge_per_kw": float(case["demand_charge_per_kw"]),
            "degradation_cost_per_kwh": float(case["degradation_cost_per_kwh"]),
            "load_forecast_kw": _forecast(case["load_kw"], t),
            "pv_forecast_kw": _forecast(case["pv_kw"], t),
            "buy_price_forecast": _forecast(case["buy_price"], t),
            "sell_price_forecast": _forecast(case["sell_price"], t),
        }
        raw_action = dispatch_action(state)
        try:
            requested = float(raw_action)
        except Exception as exc:
            raise ValueError(f"dispatch_action returned non-numeric value at t={t}: {raw_action!r}") from exc
        if not math.isfinite(requested):
            raise ValueError(f"dispatch_action returned non-finite value at t={t}: {requested!r}")

        charge_limit = min(max_charge, max(0.0, (capacity - soc) / max(charge_eff, 1e-9)))
        discharge_limit = min(max_discharge, max(0.0, (soc - min_soc) * max(discharge_eff, 1e-9)))
        applied = max(-charge_limit, min(discharge_limit, requested))
        infeasible_penalty += abs(requested - applied) * 1.5

        if applied >= 0.0:
            soc -= applied / max(discharge_eff, 1e-9)
        else:
            soc += (-applied) * charge_eff
        soc = min(capacity, max(min_soc, soc))

        load = float(case["load_kw"][t])
        pv = float(case["pv_kw"][t])
        grid_kw = load - pv - applied
        grid_import = max(0.0, grid_kw)
        grid_export = max(0.0, -grid_kw)
        import_cost += grid_import * float(case["buy_price"][t])
        export_credit += grid_export * float(case["sell_price"][t])
        throughput_kwh += abs(applied)
        degradation_cost += abs(applied) * float(case["degradation_cost_per_kwh"])
        peak_import_kw = max(peak_import_kw, grid_import)
        actions.append(applied)
        soc_trace.append(soc)

    demand_charge = peak_import_kw * float(case["demand_charge_per_kw"])
    total_cost = import_cost - export_credit + degradation_cost + demand_charge + infeasible_penalty
    return {
        "case_id": case["case_id"],
        "total_cost": total_cost,
        "import_cost": import_cost,
        "export_credit": export_credit,
        "degradation_cost": degradation_cost,
        "demand_charge": demand_charge,
        "infeasible_penalty": infeasible_penalty,
        "peak_import_kw": peak_import_kw,
        "throughput_kwh": throughput_kwh,
        "final_soc_kwh": soc,
        "mean_action_kw": statistics.fmean(actions) if actions else 0.0,
        "soc_min_kwh": min(soc_trace),
        "soc_max_kwh": max(soc_trace),
    }


def evaluate(candidate_path: str) -> tuple[dict[str, float], dict[str, Any]]:
    module = _load_candidate(Path(candidate_path).resolve())
    dispatch_action = getattr(module, "dispatch_action", None)
    if dispatch_action is None:
        raise AttributeError("candidate must define dispatch_action(state)")

    case_results = [_simulate_case(dispatch_action, case) for case in _build_cases()]
    mean_cost = statistics.fmean(float(item["total_cost"]) for item in case_results)
    mean_peak = statistics.fmean(float(item["peak_import_kw"]) for item in case_results)
    mean_penalty = statistics.fmean(float(item["infeasible_penalty"]) for item in case_results)
    metrics = {
        "combined_score": -float(mean_cost),
        "valid": 1.0,
        "mean_total_cost": float(mean_cost),
        "mean_peak_import_kw": float(mean_peak),
        "mean_infeasible_penalty": float(mean_penalty),
    }
    artifacts = {
        "case_results": case_results,
        "score_direction": "higher_is_better",
    }
    return metrics, artifacts


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate")
    parser.add_argument("--metrics-out", default="metrics.json")
    parser.add_argument("--artifacts-out", default="artifacts.json")
    args = parser.parse_args(argv)

    start = time.time()
    try:
        metrics, artifacts = evaluate(args.candidate)
    except Exception as exc:
        metrics = {
            "combined_score": INVALID_COMBINED_SCORE,
            "valid": 0.0,
            "runtime_s": float(time.time() - start),
        }
        artifacts = {
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
        }
    metrics["runtime_s"] = float(time.time() - start)
    artifacts["candidate_path"] = str(Path(args.candidate).resolve())
    _write_json(args.metrics_out, metrics)
    _write_json(args.artifacts_out, artifacts)
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
