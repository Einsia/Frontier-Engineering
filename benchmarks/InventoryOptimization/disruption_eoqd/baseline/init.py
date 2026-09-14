# EVOLVE-BLOCK-START
"""Baseline implementation for Task 05.

No stockpyl EOQD optimizer is used here.

Contract
--------
This file runs as a *standalone program* in an isolated working directory. The
evaluator stages the instance in ``config.json`` next to it, runs it in a
subprocess, and then reads only ``submission.json``:

    {"order_quantity": <float, finite and > 0>}

The evaluator recomputes every score input itself (including the classic-EOQ
comparison anchor), so nothing this file reports other than the order quantity
can influence the score.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

DEFAULT_CFG = {
    "fixed_cost": 120.0,
    "holding_cost": 1.8,
    "stockout_cost": 14.0,
    "demand_rate": 80.0,
    "disruption_rate": 0.08,
    "recovery_rate": 0.35,
}


def load_config() -> dict:
    """Read the instance staged by the evaluator (falls back to the default)."""
    path = Path("config.json")
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return dict(DEFAULT_CFG)


def classic_eoq(fixed_cost: float, holding_cost: float, demand_rate: float) -> float:
    return math.sqrt(2.0 * fixed_cost * demand_rate / holding_cost)


def solve(cfg: dict) -> float:
    """Return the order quantity Q to use under disruption risk."""
    q_classic = classic_eoq(cfg["fixed_cost"], cfg["holding_cost"], cfg["demand_rate"])
    safety_multiplier = 1.0 + 0.5 * cfg["disruption_rate"] / cfg["recovery_rate"]
    return q_classic * safety_multiplier


def _write_submission(order_quantity: float) -> None:
    Path("submission.json").write_text(
        json.dumps({"order_quantity": float(order_quantity)}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    _write_submission(solve(load_config()))
# EVOLVE-BLOCK-END
