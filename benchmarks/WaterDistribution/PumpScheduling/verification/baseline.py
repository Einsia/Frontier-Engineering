"""Frozen reference controller for evaluator normalization."""


def control(observation: dict) -> dict[str, float]:
    hour = int(observation["hour"])
    tank_1 = float(observation["tank_levels_m"]["1"])
    price = float(observation["tariff"])
    pump_10 = 1.0 if hour in range(1, 21) else 0.0
    if min(observation["tank_levels_m"].values()) < 2.5:
        pump_10 = 1.0
    if tank_1 < 5.25:
        pump_335 = 1.0
    elif tank_1 > 5.80:
        pump_335 = 0.0
    else:
        pump_335 = 0.0 if price > 0.20 else float(observation["previous_action"]["335"])
    return {"10": pump_10, "335": pump_335}
