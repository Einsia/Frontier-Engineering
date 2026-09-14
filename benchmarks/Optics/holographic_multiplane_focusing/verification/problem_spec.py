"""Scorer-owned problem definition for multi-plane focusing.

Observation planes, spot coordinates and target power ratios are defined here
and loaded by the evaluator before candidate execution.
"""

from __future__ import annotations

from typing import Any

TASK_NAME = "task2_multiplane_focusing"

WAIST_RADIUS = 130e-6

#: Sanity bound on a submitted phase value (radians); see problem_spec of H1.
MAX_ABS_PHASE = 1.0e4


def make_spec(*, baseline_steps: int = 24, reference_steps: int = 40) -> dict[str, Any]:
    waist = WAIST_RADIUS
    spacing = 10e-6
    spec: dict[str, Any] = {
        # --- optical model (scorer-owned) ---
        "shape": 72,
        "spacing": spacing,
        "wavelength": 700e-9,
        "waist_radius": waist,
        "layer_z": [0.0, 0.12, 0.24, 0.36],
        # --- targets (scorer-owned) ---
        "planes": [
            {
                "z": 0.48,
                "centers": [(-2.2 * waist, -1.4 * waist), (0.0, -1.9 * waist), (2.2 * waist, -1.4 * waist)],
                "ratios": [0.50, 0.30, 0.20],
            },
            {
                "z": 0.62,
                "centers": [(-2.0 * waist, 1.8 * waist), (0.0, 1.2 * waist), (2.0 * waist, 1.8 * waist)],
                "ratios": [0.20, 0.55, 0.25],
            },
            {
                "z": 0.76,
                "centers": [(-1.8 * waist, 0.0), (0.0, 0.0), (1.8 * waist, 0.0)],
                "ratios": [0.25, 0.50, 0.25],
            },
        ],
        "roi_radius_m": 3 * spacing,
        # --- scoring constants (scorer-owned) ---
        "valid_mean_ratio_mae_max": 0.34,
        "valid_mean_efficiency_min": 0.015,
        "valid_mean_score_min": 0.18,
        "score_eff_target": 0.09,
        "score_ratio_scale": 0.12,
        "better_score_margin": 0.07,
        "better_shape_margin": 0.03,
        # --- budgets ---
        "steps": int(baseline_steps),
        "lr": 0.075,
        "reference_steps": int(reference_steps),
        "reference_lr": 0.045,
        # --- submission contract ---
        "max_abs_phase": MAX_ABS_PHASE,
    }
    spec["n_layers"] = len(spec["layer_z"])
    spec["phase_shape"] = [spec["n_layers"], spec["shape"], spec["shape"]]
    return spec


def candidate_problem(spec: dict[str, Any]) -> dict[str, Any]:
    """The JSON handed to the candidate subprocess -- data only, never authority."""
    keys = (
        "shape",
        "spacing",
        "wavelength",
        "waist_radius",
        "layer_z",
        "planes",
        "roi_radius_m",
        "score_eff_target",
        "score_ratio_scale",
        "valid_mean_ratio_mae_max",
        "valid_mean_efficiency_min",
        "valid_mean_score_min",
        "steps",
        "lr",
        "n_layers",
        "phase_shape",
        "max_abs_phase",
    )
    problem = {k: spec[k] for k in keys}
    problem["submission"] = {
        "file": "submission.npz",
        "arrays": {
            "phases": {
                "shape": spec["phase_shape"],
                "dtype": "float64",
                "units": "radians",
                "description": (
                    "Phase map of each PhaseModulator layer, in the order of layer_z. "
                    "One shared stack serves all observation planes; the evaluator "
                    "propagates to every plane in spec['planes'] itself."
                ),
            }
        },
        "optional_arrays": {
            "loss_history": "1-D float array, diagnostics only; never scored.",
        },
    }
    return problem
