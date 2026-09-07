#!/usr/bin/env python
"""Scorer-owned forward model and metrics for Task 01.

``forward_intensity`` used to be a candidate-supplied function and the metrics
were computed from whatever intensity that function chose to return. Both are
now fixed here, so all eight models on the leaderboard are measured with one
ruler.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np

from problem import common

SPOT_WINDOW_RADIUS_PX = 1

VALID_THRESHOLDS = {
    "score_min": 0.20,
    "score_pct_min": 20.0,
    "efficiency_min": 0.45,
    "min_peak_ratio_min": 0.0,
}


def forward_intensity(problem: Dict[str, Any], phase: np.ndarray) -> np.ndarray:
    return common.far_field_intensity(problem["aperture_amp"], phase)


def score_from_metrics(
    ratio_mae: float,
    cv_spots: float,
    efficiency: float,
    min_peak_ratio: float,
) -> float:
    ratio_score = np.clip(1.0 - ratio_mae / 0.07, 0.0, 1.0)
    uniform_score = 1.0 / (1.0 + (cv_spots / 0.85) ** 2)
    efficiency_score = np.clip((efficiency - 0.15) / (0.80 - 0.15), 0.0, 1.0)
    peak_score = np.clip((min_peak_ratio - 0.003) / (0.20 - 0.003), 0.0, 1.0)

    return float(
        0.25 * ratio_score + 0.45 * uniform_score + 0.20 * efficiency_score + 0.10 * peak_score
    )


def spot_metrics(
    problem: Dict[str, Any],
    intensity: np.ndarray,
    window_radius_px: int = SPOT_WINDOW_RADIUS_PX,
) -> Dict[str, Any]:
    spot_energies, spot_peaks = common.spot_window_energies(
        intensity, problem["spots"], window_radius_px
    )

    ratios = spot_energies / (spot_energies.sum() + 1e-12)
    target = problem["weights"]

    ratio_mae = float(np.mean(np.abs(ratios - target)))
    cv_spots = float(spot_energies.std() / (spot_energies.mean() + 1e-12))
    efficiency = float(spot_energies.sum() / (intensity.sum() + 1e-12))
    min_peak_ratio = float(spot_peaks.min() / (spot_peaks.max() + 1e-12))

    score = score_from_metrics(ratio_mae, cv_spots, efficiency, min_peak_ratio)

    return {
        "ratio_mae": ratio_mae,
        "cv_spots": cv_spots,
        "efficiency": efficiency,
        "min_peak_ratio": min_peak_ratio,
        "score": score,
        "score_pct": float(100.0 * score),
        "spot_ratios": ratios.tolist(),
        "target_ratios": np.asarray(target, dtype=float).tolist(),
        "spot_peaks": spot_peaks.tolist(),
    }


def evaluate_phase(problem: Dict[str, Any], phase: np.ndarray) -> tuple[Dict[str, Any], np.ndarray]:
    """The only path from a decision variable to a score."""
    intensity = forward_intensity(problem, phase)
    return spot_metrics(problem, intensity), intensity


def is_valid(metrics: Dict[str, Any]) -> bool:
    return bool(
        metrics["score"] >= VALID_THRESHOLDS["score_min"]
        and metrics["efficiency"] >= VALID_THRESHOLDS["efficiency_min"]
        and metrics["min_peak_ratio"] > VALID_THRESHOLDS["min_peak_ratio_min"]
    )
