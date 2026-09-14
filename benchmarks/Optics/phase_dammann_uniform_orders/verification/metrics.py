#!/usr/bin/env python
"""Scorer-owned forward model and metrics for Dammann uniform orders.

Candidates supply transition positions. The scorer constructs the incident
field and computes order energies and uniformity from those positions.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np
from diffractio.scalar_masks_X import Scalar_mask_X

from problem import common

VALID_THRESHOLDS = {
    "cv_orders_max": 0.8,
    "efficiency_min": 0.003,
    "min_to_max_min": 0.15,
}


def build_incident_field(problem: Dict[str, Any], transitions: np.ndarray) -> Scalar_mask_X:
    cfg = problem["cfg"]
    x_period = problem["x_period"]

    period = Scalar_mask_X(x=x_period, wavelength=cfg["wavelength"])
    period.binary_code_positions(x_transitions=transitions, start="down", has_draw=False)
    period.u = np.exp(1j * np.pi * period.u)

    dammann = period.repeat_structure(
        num_repetitions=cfg["num_repetitions"],
        position="center",
        new_field=True,
    )

    lens = Scalar_mask_X(x=dammann.x, wavelength=cfg["wavelength"])
    lens.lens(x0=0.0, focal=cfg["focal"], radius=cfg["lens_radius"])

    return dammann * lens


def propagate_to_focus(problem: Dict[str, Any], transitions: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    field = build_incident_field(problem, transitions)
    focus = field.RS(z=problem["cfg"]["focal"], new_field=True, verbose=False)
    return np.asarray(focus.x), np.abs(focus.u) ** 2


def evaluate_orders(problem: Dict[str, Any], intensity_x: np.ndarray, x: np.ndarray) -> Dict[str, Any]:
    cfg = problem["cfg"]
    spacing = cfg["focal"] * cfg["wavelength"] / cfg["period_size"]

    orders = np.arange(cfg["order_min"], cfg["order_max"] + 1, dtype=int)
    energies = []
    positions = []

    hw = int(cfg["order_window_halfwidth_px"])
    for m in orders:
        x_m = m * spacing
        ix = int(np.argmin(np.abs(x - x_m)))
        i0 = max(0, ix - hw)
        i1 = min(len(x), ix + hw + 1)
        energies.append(float(intensity_x[i0:i1].sum()))
        positions.append(float(x_m))

    energies = np.asarray(energies, dtype=float)
    cv = float(energies.std() / (energies.mean() + 1e-12))
    norm = energies / (energies.max() + 1e-12)
    efficiency = float(energies.sum() / (intensity_x.sum() + 1e-12))

    return {
        "orders": orders.tolist(),
        "order_positions": positions,
        "order_energies": energies.tolist(),
        "order_energies_norm": norm.tolist(),
        "cv_orders": cv,
        "efficiency": efficiency,
        "min_to_max": float(norm.min()),
    }


def score_pct(metrics: Dict[str, Any]) -> float:
    """User-facing score in [0, 100], higher is better."""
    uniform_score = np.clip(1.0 - metrics["cv_orders"] / 0.9, 0.0, 1.0)
    efficiency_score = np.clip((metrics["efficiency"] - 0.003) / (0.18 - 0.003), 0.0, 1.0)
    balance_score = np.clip((metrics["min_to_max"] - 0.15) / (0.90 - 0.15), 0.0, 1.0)
    return float(100.0 * (0.60 * uniform_score + 0.30 * efficiency_score + 0.10 * balance_score))


def loss(metrics: Dict[str, Any]) -> float:
    """Lower-is-better surrogate used internally by the DE oracle."""
    return float(metrics["cv_orders"] + 0.2 * (1.0 - metrics["efficiency"]))


def evaluate_transitions(
    problem: Dict[str, Any], transitions: np.ndarray
) -> Tuple[Dict[str, Any], np.ndarray, np.ndarray]:
    """The only path from a decision variable to a score."""
    x_focus, intensity = propagate_to_focus(problem, transitions)
    metrics = evaluate_orders(problem, intensity, x_focus)
    metrics["score_pct"] = score_pct(metrics)
    return metrics, x_focus, intensity


def is_valid(metrics: Dict[str, Any]) -> bool:
    return bool(
        metrics["cv_orders"] <= VALID_THRESHOLDS["cv_orders_max"]
        and metrics["efficiency"] >= VALID_THRESHOLDS["efficiency_min"]
        and metrics["min_to_max"] >= VALID_THRESHOLDS["min_to_max_min"]
    )
