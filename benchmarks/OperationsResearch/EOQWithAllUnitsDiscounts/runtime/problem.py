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
        "breakpoints": [
            0.0,
            350.0,
            700.0
        ],
        "unit_costs": [
            0.5,
            0.47,
            0.44
        ]
    },
    {
        "fixed_cost": 10.0,
        "holding_cost_rate": 0.18,
        "demand_rate": 2200.0,
        "breakpoints": [
            0.0,
            300.0,
            900.0
        ],
        "unit_costs": [
            0.82,
            0.79,
            0.73
        ]
    },
    {
        "fixed_cost": 12.0,
        "holding_cost_rate": 0.2,
        "demand_rate": 1700.0,
        "breakpoints": [
            0.0,
            500.0,
            1000.0
        ],
        "unit_costs": [
            1.1,
            1.03,
            0.98
        ]
    },
    {
        "fixed_cost": 6.0,
        "holding_cost_rate": 0.16,
        "demand_rate": 2400.0,
        "breakpoints": [
            0.0,
            250.0,
            600.0
        ],
        "unit_costs": [
            0.42,
            0.39,
            0.36
        ]
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

def _region(instance: dict[str, float], q: float) -> int:
    region = 0
    for idx, bp in enumerate(instance["breakpoints"]):
        if q >= bp:
            region = idx
    return region


def _cost(instance: dict[str, float], q: float) -> float:
    region = _region(instance, q)
    unit_cost = instance["unit_costs"][region]
    return (
        unit_cost * instance["demand_rate"]
        + instance["fixed_cost"] * instance["demand_rate"] / q
        + instance["holding_cost_rate"] * unit_cost * q / 2.0
    )


def solve_baseline(instance: dict[str, float]) -> dict[str, float]:
    q, region, cost = economic_order_quantity_with_all_units_discounts(
        instance["fixed_cost"],
        instance["holding_cost_rate"],
        instance["demand_rate"],
        list(instance["breakpoints"]),
        list(instance["unit_costs"]),
    )
    return {"order_quantity": float(q), "region": int(region), "cost": float(cost)}


def evaluate_solution(instance: dict[str, float], solution: Any) -> dict[str, float | bool]:
    try:
        q = _extract_order_quantity(solution)
    except Exception:
        return {"valid": False, "cost": float("inf")}
    if q <= 0:
        return {"valid": False, "cost": float("inf")}
    return {"valid": True, "cost": float(_cost(instance, q)), "order_quantity": float(q)}
