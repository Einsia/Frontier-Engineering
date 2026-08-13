"""Recorded baseline; intentionally identical to scripts/init.py."""

from __future__ import annotations

from typing import Any


def design_laminates(cases: list[dict[str, Any]]) -> dict[str, list[int]]:
    haftka_reference = [90, 45, 45, 90, 45, 90, 45, 45, 45, 45, 45, 45]
    return {str(case["case_id"]): list(haftka_reference) for case in cases}
