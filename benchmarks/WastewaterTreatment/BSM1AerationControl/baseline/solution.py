"""Reference fixed-operating-point policy for BSM1AerationControl."""

from __future__ import annotations


def reset_controller(scenario: dict) -> None:
    pass


def control(observation: dict) -> dict:
    return {
        "kla3_per_day": 240.0,
        "kla4_per_day": 240.0,
        "kla5_per_day": 84.0,
        "internal_recycle_m3_per_day": 55338.0,
    }
