"""Scorer-owned problem definition for Holographic H4 (polarization multiplexing).

This file used to be ``make_default_spec()`` inside ``baseline/init.py``. This
task was the most exposed of the four: the old evaluator read
``result["output_field_x"]``, ``result["output_field_y"]``, ``result["target_map_x"]``
and ``result["target_map_y"]`` straight from the candidate, i.e. the candidate
supplied *both* sides of every comparison and no propagation happened in the
evaluator at all.

Now the spec lives here, the candidate submits only the Jones phase maps, and
``verification/evaluate.py`` builds the inputs, runs the propagation and builds
the targets itself.
"""

from __future__ import annotations

from typing import Any

TASK_NAME = "task4_polarization_multiplexing"

WAIST_RADIUS = 90e-6

#: Sanity bound on a submitted phase value (radians); see problem_spec of H1.
MAX_ABS_PHASE = 1.0e4


def make_spec(*, baseline_steps: int = 24, reference_steps: int = 40) -> dict[str, Any]:
    waist = WAIST_RADIUS
    spacing = 10e-6
    spec: dict[str, Any] = {
        # --- optical model (scorer-owned) ---
        "shape": 40,
        "spacing": spacing,
        "wavelength": 700e-9,
        "waist_radius": waist,
        "layer_z": [0.08, 0.20],
        "output_z": 0.54,
        # --- targets (scorer-owned) ---
        "pattern_x_centers": [(-1.9 * waist, -1.3 * waist), (0.0, 0.0), (1.9 * waist, 1.3 * waist)],
        "pattern_x_ratios": [0.50, 0.30, 0.20],
        "pattern_y_centers": [(-1.9 * waist, 1.3 * waist), (0.0, 0.0), (1.9 * waist, -1.3 * waist)],
        "pattern_y_ratios": [0.25, 0.35, 0.40],
        "roi_radius_m": 3 * spacing,
        # --- scoring constants (scorer-owned) ---
        "valid_match_min": 0.32,
        "valid_separation_min": 0.42,
        "valid_score_min": 0.16,
        "score_eff_target": 0.20,
        "score_ratio_scale": 0.10,
        "better_score_margin": 0.10,
        "better_sep_margin": 0.10,
        # --- budgets ---
        "steps": int(baseline_steps),
        "lr": 0.045,
        "reference_steps": int(reference_steps),
        "reference_lr": 0.04,
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
        "output_z",
        "pattern_x_centers",
        "pattern_x_ratios",
        "pattern_y_centers",
        "pattern_y_ratios",
        "roi_radius_m",
        "score_eff_target",
        "score_ratio_scale",
        "valid_match_min",
        "valid_separation_min",
        "valid_score_min",
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
            "phase_x": {
                "shape": spec["phase_shape"],
                "dtype": "float64",
                "units": "radians",
                "description": "Jones [0,0] phase of each layer, in the order of layer_z.",
            },
            "phase_y": {
                "shape": spec["phase_shape"],
                "dtype": "float64",
                "units": "radians",
                "description": "Jones [1,1] phase of each layer, in the order of layer_z.",
            },
        },
        "optional_arrays": {
            "loss_history": "1-D float array, diagnostics only; never scored.",
        },
        "forward_model": (
            "For each layer: propagate_to_z(layer_z[i]), then polarized_modulate with "
            "diag(exp(1j*phase_x[i]), exp(1j*phase_y[i]), 1). Finally propagate_to_z(output_z). "
            "The evaluator runs this itself for both the x- and y-polarised input."
        ),
    }
    return problem
