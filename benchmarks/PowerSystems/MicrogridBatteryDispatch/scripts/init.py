from __future__ import annotations

from typing import Any


def dispatch_action(state: dict[str, Any]) -> float:
    """Return battery power in kW: positive discharges, negative charges."""

    # EVOLVE-BLOCK-START
    soc = float(state["soc_kwh"])
    capacity = float(state["capacity_kwh"])
    min_soc = float(state["min_soc_kwh"])
    max_discharge = float(state["max_discharge_kw"])
    discharge_eff = float(state["discharge_efficiency"])

    load_forecast = [float(x) for x in state["load_forecast_kw"][:24]]
    pv_forecast = [float(x) for x in state["pv_forecast_kw"][:24]]
    net_forecast = [load - pv for load, pv in zip(load_forecast, pv_forecast)]
    net_load = net_forecast[0] if net_forecast else 0.0

    discharge_room_kw = max(0.0, (soc - min_soc) * max(discharge_eff, 1e-9))
    reserve_soc = min(capacity, min_soc + 0.05 * (capacity - min_soc))
    available_discharge = min(discharge_room_kw, max(0.0, (soc - reserve_soc) * discharge_eff))
    future_peak = max(net_forecast) if net_forecast else net_load
    peak_target = max(90.0, 0.90 * future_peak)
    shave_kw = max(0.0, net_load - peak_target)

    if shave_kw > 0.0 and available_discharge > 0.0:
        return min(max_discharge, shave_kw, available_discharge)

    return 0.0
    # EVOLVE-BLOCK-END


if __name__ == "__main__":
    demo_state = {
        "soc_kwh": 90.0,
        "min_soc_kwh": 20.0,
        "capacity_kwh": 160.0,
        "max_charge_kw": 45.0,
        "max_discharge_kw": 45.0,
        "charge_efficiency": 0.94,
        "discharge_efficiency": 0.93,
        "load_forecast_kw": [120.0] * 24,
        "pv_forecast_kw": [80.0] * 24,
        "buy_price_forecast": [0.18] * 24,
        "sell_price_forecast": [0.05] * 24,
    }
    print(dispatch_action(demo_state))
