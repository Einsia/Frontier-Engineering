"""Baseline controller for the Net3 pump-scheduling task."""


# EVOLVE-BLOCK-START
def control(observation: dict) -> dict[str, float]:
    """Return pump speeds using only causal information in ``observation``."""
    hour = int(observation["hour"])
    tank_1 = float(observation["tank_levels_m"]["1"])
    price = float(observation["tariff"])

    # Pump 10 replenishes the network from the lake, mostly off peak.
    pump_10 = 1.0 if hour in range(1, 21) else 0.0
    if min(observation["tank_levels_m"].values()) < 2.5:
        pump_10 = 1.0

    # Pump 335 and pipe 330 regulate tank 1 in the original Net3 controls.
    if tank_1 < 5.25:
        pump_335 = 1.0
    elif tank_1 > 5.80:
        pump_335 = 0.0
    else:
        pump_335 = 0.0 if price > 0.20 else float(observation["previous_action"]["335"])
    return {"10": pump_10, "335": pump_335}
# EVOLVE-BLOCK-END
