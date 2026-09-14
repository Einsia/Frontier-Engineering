#!/usr/bin/env python
"""Scorer-owned forward model and metrics for Task 02."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np

from problem import common

ENERGY_THRESHOLD = 0.30
DARK_THRESHOLD = 0.03

VALID_THRESHOLDS = {
    "score_pct_min": 20.0,
    "energy_in_target_min": 0.45,
    "dark_suppression_min": 0.60,
}


def forward_intensity(problem: Dict[str, Any], phase: np.ndarray) -> np.ndarray:
    return common.far_field_intensity(problem["aperture_amp"], phase)


def nmse(intensity: np.ndarray, target_amp: np.ndarray) -> float:
    target_intensity = target_amp**2
    I_n = intensity / (intensity.mean() + 1e-12)
    T_n = target_intensity / (target_intensity.mean() + 1e-12)
    return float(np.sqrt(((I_n - T_n) ** 2).mean()))


def energy_in_target(intensity: np.ndarray, target_amp: np.ndarray, threshold: float = ENERGY_THRESHOLD) -> float:
    mask = target_amp > threshold
    return float(intensity[mask].sum() / (intensity.sum() + 1e-12))


def dark_suppression(intensity: np.ndarray, target_amp: np.ndarray, threshold: float = DARK_THRESHOLD) -> float:
    mask_dark = target_amp < threshold
    leak = float(intensity[mask_dark].sum() / (intensity.sum() + 1e-12))
    return float(1.0 - leak)


def score_from_metrics(nmse_value: float, energy_target: float, dark_sup: float) -> float:
    pattern_score = np.clip(1.0 - nmse_value / 4.0, 0.0, 1.0)
    energy_score = np.clip((energy_target - 0.10) / (0.70 - 0.10), 0.0, 1.0)
    dark_score = np.clip((dark_sup - 0.35) / (0.90 - 0.35), 0.0, 1.0)

    return float(100.0 * (0.55 * pattern_score + 0.30 * energy_score + 0.15 * dark_score))


def evaluate_phase(problem: Dict[str, Any], phase: np.ndarray) -> tuple[Dict[str, Any], np.ndarray]:
    """The only path from a decision variable to a score."""
    intensity = forward_intensity(problem, phase)
    target_amp = problem["target_amp"]

    nmse_value = nmse(intensity, target_amp)
    energy = energy_in_target(intensity, target_amp)
    dark = dark_suppression(intensity, target_amp)

    return (
        {
            "nmse": float(nmse_value),
            "energy_in_target": float(energy),
            "dark_suppression": float(dark),
            "score_pct": float(score_from_metrics(nmse_value, energy, dark)),
        },
        intensity,
    )


def is_valid(metrics: Dict[str, Any]) -> bool:
    return bool(
        metrics["score_pct"] >= VALID_THRESHOLDS["score_pct_min"]
        and metrics["energy_in_target"] >= VALID_THRESHOLDS["energy_in_target_min"]
        and metrics["dark_suppression"] >= VALID_THRESHOLDS["dark_suppression_min"]
    )
