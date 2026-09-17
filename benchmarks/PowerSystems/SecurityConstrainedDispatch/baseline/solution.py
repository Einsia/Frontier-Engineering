from __future__ import annotations

from typing import Any


def solve(case: dict[str, Any]) -> dict[str, list[float]]:
    """Released feasible, deliberately non-optimal baseline."""

    generators = case["generators"]
    return {
        "pg_mw": [float(generator["baseline_pg_mw"]) for generator in generators],
        "vg_pu": [float(generator["baseline_vg_pu"]) for generator in generators],
    }
