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
        "fixed_cost": 8.0,
        "holding_cost_rate": 0.225,
        "demand_rate": 1300.0,
        "minimum_order_quantity": 80.0
    },
    {
        "fixed_cost": 14.0,
        "holding_cost_rate": 0.18,
        "demand_rate": 1800.0,
        "minimum_order_quantity": 140.0
    },
    {
        "fixed_cost": 11.0,
        "holding_cost_rate": 0.25,
        "demand_rate": 950.0,
        "minimum_order_quantity": 100.0
    },
    {
        "fixed_cost": 6.0,
        "holding_cost_rate": 0.16,
        "demand_rate": 2200.0,
        "minimum_order_quantity": 120.0
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

def solve_baseline(instance: dict[str, float]) -> dict[str, float]:
    q_star, _ = economic_order_quantity(
        instance["fixed_cost"],
        instance["holding_cost_rate"],
        instance["demand_rate"],
    )
    q = max(q_star, instance["minimum_order_quantity"])
    return {"order_quantity": float(q)}


def evaluate_solution(instance: dict[str, float], solution: Any) -> dict[str, float | bool]:
    try:
        q = _extract_order_quantity(solution)
    except Exception:
        return {"valid": False, "cost": float("inf")}
    if q < instance["minimum_order_quantity"] or q <= 0:
        return {"valid": False, "cost": float("inf")}
    _, cost = economic_order_quantity(
        instance["fixed_cost"],
        instance["holding_cost_rate"],
        instance["demand_rate"],
        order_quantity=q,
    )
    return {"valid": True, "cost": float(cost), "order_quantity": float(q)}
