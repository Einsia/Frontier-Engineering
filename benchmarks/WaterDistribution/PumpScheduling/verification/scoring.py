import math


def scenario_score(metrics, reference):
    if not metrics.get("valid", False):
        return 0.0
    ratios = {
        "energy": reference["energy_cost"] / max(metrics["energy_cost"], 1e-9),
        "peak": reference["peak_power_kw"] / max(metrics["peak_power_kw"], 1e-9),
        "smooth": reference["switching"] / max(metrics["switching"], 1e-9),
        "terminal": reference["terminal_deficit_m"] / max(metrics["terminal_deficit_m"], 1e-9),
    }
    bounded = {k: min(1.5, max(0.0, v)) for k, v in ratios.items()}
    return 100.0 * (0.55 * bounded["energy"] + 0.20 * bounded["peak"] + 0.10 * bounded["smooth"] + 0.15 * bounded["terminal"])


def aggregate(scores):
    if not scores or any(not math.isfinite(x) or x <= 0 for x in scores):
        return 0.0
    return 0.70 * sum(scores) / len(scores) + 0.30 * min(scores)
