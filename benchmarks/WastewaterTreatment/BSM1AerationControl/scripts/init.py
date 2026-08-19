"""Editable baseline controller for the BSM1 aeration benchmark."""

from __future__ import annotations


def reset_controller(scenario: dict) -> None:
    """Reset any candidate-owned state before a weather scenario."""


def control(observation: dict) -> dict:
    """Return aeration coefficients and the internal recycle flow."""

    # EVOLVE-BLOCK-START
    return {
        "kla3_per_day": 240.0,
        "kla4_per_day": 240.0,
        "kla5_per_day": 84.0,
        "internal_recycle_m3_per_day": 55338.0,
    }
    # EVOLVE-BLOCK-END
