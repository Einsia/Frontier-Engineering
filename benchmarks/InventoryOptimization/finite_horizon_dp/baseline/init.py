# EVOLVE-BLOCK-START
"""Baseline implementation for Task 04.

No stockpyl DP solver is used here.

Contract
--------
This file runs as a *standalone program* in an isolated working directory. The
evaluator stages the instance in ``config.json`` next to it, runs it in a
subprocess, and then reads only ``submission.json``:

    {"reorder_points": [s_1, ..., s_T], "order_up_to_levels": [S_1, ..., S_T]}

Both lists must have exactly ``num_periods`` entries with ``0 <= s_t <= S_t``.
The evaluator re-runs the Monte-Carlo simulation from this policy itself, so
nothing else this file could report would matter.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CFG = {
    "num_periods": 8,
    "demand_mean": [40, 45, 55, 80, 95, 70, 50, 45],
    "demand_sd": [8, 9, 12, 15, 18, 14, 10, 9],
}


def load_config() -> dict:
    """Read the instance staged by the evaluator (falls back to the default)."""
    path = Path("config.json")
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return dict(DEFAULT_CFG)


def solve(demand_mean, demand_sd):
    """Manual moment-based time-varying policy.

    Rule:
    - s_t = round(0.60 * mean_t)
    - S_t = round(mean_t + 1.10 * sd_t + 32), with S_t >= s_t + 6
    """

    s_levels = [round(0.60 * m) for m in demand_mean]
    S_levels = []
    for i, (m, sd) in enumerate(zip(demand_mean, demand_sd)):
        s_t = s_levels[i]
        S_t = round(m + 1.10 * sd + 32)
        S_levels.append(max(S_t, s_t + 6))

    return s_levels, S_levels


def _write_submission(s_levels, S_levels) -> None:
    Path("submission.json").write_text(
        json.dumps(
            {"reorder_points": list(s_levels), "order_up_to_levels": list(S_levels)},
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    cfg = load_config()
    _write_submission(*solve(cfg["demand_mean"], cfg["demand_sd"]))
# EVOLVE-BLOCK-END
