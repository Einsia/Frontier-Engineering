from __future__ import annotations

from typing import Any


def solve(case: dict[str, Any]) -> dict[str, list[float]]:
    """Return active-power and voltage setpoints for every generator.

    The baseline uses a precomputed feasible but deliberately non-optimal
    dispatch. Improve the logic inside the EVOLVE block while preserving the
    function signature and output schema.
    """

    # EVOLVE-BLOCK-START
    generators = case["generators"]
    return {
        "pg_mw": [float(generator["baseline_pg_mw"]) for generator in generators],
        "vg_pu": [float(generator["baseline_vg_pu"]) for generator in generators],
    }
    # EVOLVE-BLOCK-END
