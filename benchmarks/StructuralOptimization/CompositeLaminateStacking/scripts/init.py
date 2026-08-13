"""Feasible starting design for CompositeLaminateStacking."""

from __future__ import annotations

from typing import Any


def design_laminates(cases: list[dict[str, Any]]) -> dict[str, list[int]]:
    """Return twelve non-negative integer base angles for every requested case."""

    # EVOLVE-BLOCK-START
    haftka_reference = [90, 45, 45, 90, 45, 90, 45, 45, 45, 45, 45, 45]
    return {str(case["case_id"]): list(haftka_reference) for case in cases}
    # EVOLVE-BLOCK-END
