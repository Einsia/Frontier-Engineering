#!/usr/bin/env python
"""Scorer-owned forward model and metrics for Task 04."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np

from problem import common

SPOT_WINDOW_RADIUS_PX = 2

VALID_THRESHOLDS = {
    "score_pct_min": 20.0,
    "ratio_mae_max": 0.03,
    "cv_spots_max": 1.40,
    "efficiency_min": 0.50,
}


def forward_intensity(problem: Dict[str, Any], phase: np.ndarray) -> np.ndarray:
    return common.far_field_intensity(problem["aperture_amp"], phase)


def score_from_metrics(ratio_mae: float, cv_spots: float, efficiency: float) -> float:
    ratio_score = np.clip(1.0 - ratio_mae / 0.03, 0.0, 1.0)
    uniform_score = np.clip(1.0 - cv_spots / 1.40, 0.0, 1.0)
    efficiency_score = np.clip((efficiency - 0.40) / (0.90 - 0.40), 0.0, 1.0)
    return float(100.0 * (0.45 * ratio_score + 0.35 * uniform_score + 0.20 * efficiency_score))


def spot_metrics(
    problem: Dict[str, Any],
    intensity: np.ndarray,
    window_radius_px: int = SPOT_WINDOW_RADIUS_PX,
) -> Dict[str, Any]:
    energies, _peaks = common.spot_window_energies(intensity, problem["spots"], window_radius_px)
    ratios = energies / (energies.sum() + 1e-12)

    ratio_mae = float(np.mean(np.abs(ratios - problem["weights"])))
    cv_spots = float(energies.std() / (energies.mean() + 1e-12))
    efficiency = float(energies.sum() / (intensity.sum() + 1e-12))

    return {
        "ratio_mae": ratio_mae,
        "cv_spots": cv_spots,
        "efficiency": efficiency,
        "score_pct": score_from_metrics(ratio_mae, cv_spots, efficiency),
        "spot_ratios": ratios.tolist(),
        "target_ratios": np.asarray(problem["weights"], dtype=float).tolist(),
        "spot_energies": energies.tolist(),
    }


def evaluate_phase(problem: Dict[str, Any], phase: np.ndarray) -> tuple[Dict[str, Any], np.ndarray]:
    """The only path from a decision variable to a score."""
    intensity = forward_intensity(problem, phase)
    return spot_metrics(problem, intensity), intensity


def is_valid(metrics: Dict[str, Any]) -> bool:
    return bool(
        metrics["score_pct"] >= VALID_THRESHOLDS["score_pct_min"]
        and metrics["ratio_mae"] <= VALID_THRESHOLDS["ratio_mae_max"]
        and metrics["cv_spots"] <= VALID_THRESHOLDS["cv_spots_max"]
        and metrics["efficiency"] >= VALID_THRESHOLDS["efficiency_min"]
    )
