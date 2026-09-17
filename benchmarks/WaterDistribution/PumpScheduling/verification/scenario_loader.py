import json
from pathlib import Path


def load_public():
    path = Path(__file__).parents[1] / "references" / "scenarios_public.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_hidden():
    """Frozen deterministic cases, kept in evaluator code to resist overfitting."""
    base = load_public()
    cases = []
    for index, source in enumerate(base):
        case = json.loads(json.dumps(source))
        case["id"] = f"hidden_{index + 1}"
        case["demand_multipliers"] = [round(min(1.50, x * (1.01 + 0.01 * index)), 4) for x in source["demand_multipliers"]]
        case["tariff"] = source["tariff"][3:] + source["tariff"][:3]
        case["initial_tank_offsets_m"] = {"1": -0.15 * index, "2": -0.20, "3": -0.10}
        if index == 1:
            case["leak"] = {"junction": "101", "start_hour": 8, "end_hour": 14, "area_m2": 0.00001}
        elif index == 2:
            case["leak"] = {"junction": "153", "start_hour": 16, "end_hour": 20, "area_m2": 0.000008}
        cases.append(case)
    return cases
