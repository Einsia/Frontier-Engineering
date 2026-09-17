from __future__ import annotations

import math
from typing import Any

from scipy.stats import norm, poisson
from stockpyl.eoq import (
    economic_order_quantity,
    economic_order_quantity_with_all_units_discounts,
    economic_order_quantity_with_incremental_discounts,
)
from stockpyl.rq import (
    r_q_cost,
    r_q_cost_poisson,
    r_q_eil_approximation,
    r_q_eoqss_approximation,
    r_q_loss_function_approximation,
    r_q_poisson_exact,
)

CASES = [
    {
        "holding_cost": 0.18,
        "stockout_cost": 0.7,
        "fixed_cost": 4.0,
        "demand_mean": 1300.0,
        "lead_time": 0.05,
        "target_csl": 0.95
    },
    {
        "holding_cost": 0.25,
        "stockout_cost": 0.95,
        "fixed_cost": 6.0,
        "demand_mean": 900.0,
        "lead_time": 0.1,
        "target_csl": 0.95
    },
    {
        "holding_cost": 0.14,
        "stockout_cost": 0.8,
        "fixed_cost": 5.0,
        "demand_mean": 1500.0,
        "lead_time": 0.04,
        "target_csl": 0.97
    },
    {
        "holding_cost": 0.22,
        "stockout_cost": 1.1,
        "fixed_cost": 7.0,
        "demand_mean": 700.0,
        "lead_time": 0.12,
        "target_csl": 0.95
    }
]
SAMPLE_INSTANCE = CASES[0]


def _to_float(value: Any) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("non-finite numeric value")
    return value


def _extract_order_quantity(solution: Any) -> float:
    if isinstance(solution, dict):
        if "order_quantity" not in solution:
            raise ValueError("missing order_quantity")
        return _to_float(solution["order_quantity"])
    return _to_float(solution)


def _extract_rq(solution: Any) -> tuple[int, int]:
    if isinstance(solution, dict):
        if "reorder_point" not in solution or "order_quantity" not in solution:
            raise ValueError("missing reorder_point/order_quantity")
        r = int(round(_to_float(solution["reorder_point"])))
        q = int(round(_to_float(solution["order_quantity"])))
        return r, q
    if isinstance(solution, (tuple, list)) and len(solution) == 2:
        r = int(round(_to_float(solution[0])))
        q = int(round(_to_float(solution[1])))
        return r, q
    raise ValueError("solution must be a dict or length-2 tuple/list")

def _service_level(instance: dict[str, float], r: int) -> float:
    mean_lt = instance["demand_mean"] * instance["lead_time"]
    return float(poisson.cdf(r, mean_lt))


def solve_baseline(instance: dict[str, float]) -> dict[str, float]:
    r, q, _ = r_q_poisson_exact(
        instance["holding_cost"],
        instance["stockout_cost"],
        instance["fixed_cost"],
        instance["demand_mean"],
        instance["lead_time"],
    )
    r = int(round(r))
    q = max(1, int(round(q)))
    while _service_level(instance, r) < instance["target_csl"]:
        r += 1
    return {"reorder_point": r, "order_quantity": q}


def evaluate_solution(instance: dict[str, float], solution: Any) -> dict[str, float | bool]:
    try:
        r, q = _extract_rq(solution)
    except Exception:
        return {"valid": False, "cost": float("inf")}
    if q <= 0:
        return {"valid": False, "cost": float("inf")}
    csl = _service_level(instance, r)
    if csl < instance["target_csl"]:
        return {"valid": False, "cost": float("inf")}
    cost = r_q_cost_poisson(
        r,
        q,
        instance["holding_cost"],
        instance["stockout_cost"],
        instance["fixed_cost"],
        instance["demand_mean"],
        instance["lead_time"],
    )
    return {"valid": True, "cost": float(cost), "reorder_point": int(r), "order_quantity": int(q), "service_level": float(csl)}
