"""Scorer-owned problem definition for multifocus power-ratio design.

Focus coordinates, target power ratios, grid and wavelength are defined here
and loaded by the evaluator before candidate execution.
"""

from __future__ import annotations

from typing import Any

TASK_NAME = "task1_multifocus_power_ratio"

#: Waist of the Gaussian source; also the length scale the focus grid is laid on.
WAIST_RADIUS = 130e-6

#: Sanity bound on a submitted phase value (radians). Phase only ever enters as
#: exp(1j*phase), but an unbounded magnitude destroys that exponential's
#: precision, so the scorer refuses anything wilder than this.
MAX_ABS_PHASE = 1.0e4


def make_spec(*, baseline_steps: int = 24, reference_steps: int = 40) -> dict[str, Any]:
    """The full specification: optics, targets, ROI and every scoring constant."""
    waist = WAIST_RADIUS
    spacing = 10e-6
    spec: dict[str, Any] = {
        # --- optical model (scorer-owned) ---
        "shape": 72,
        "spacing": spacing,
        "wavelength": 700e-9,
        "waist_radius": waist,
        "layer_z": [0.0, 0.12, 0.24, 0.36],
        "output_z": 0.56,
        # --- targets (scorer-owned) ---
        "focus_centers": [
            (-2.3 * waist, -1.6 * waist),
            (0.0, -2.3 * waist),
            (2.3 * waist, -1.6 * waist),
            (-2.3 * waist, 1.6 * waist),
            (0.0, 2.3 * waist),
            (2.3 * waist, 1.6 * waist),
        ],
        "focus_ratios": [0.24, 0.17, 0.16, 0.15, 0.14, 0.14],
        "roi_radius_m": 3 * spacing,
        # --- scoring constants (scorer-owned) ---
        "valid_ratio_mae_max": 0.30,
        "valid_efficiency_min": 0.040,
        "valid_score_min": 0.16,
        "score_eff_target": 0.20,
        "score_ratio_scale": 0.10,
        "better_score_margin": 0.06,
        "better_shape_margin": 0.03,
        # --- budgets ---
        "steps": int(baseline_steps),
        "lr": 0.075,
        "reference_steps": int(reference_steps),
        "reference_lr": 0.05,
        # --- submission contract ---
        "max_abs_phase": MAX_ABS_PHASE,
    }
    spec["n_layers"] = len(spec["layer_z"])
    spec["phase_shape"] = [spec["n_layers"], spec["shape"], spec["shape"]]
    return spec


def candidate_problem(spec: dict[str, Any]) -> dict[str, Any]:
    """The JSON handed to the candidate subprocess.

    Everything here is already public in ``Task.md``; withholding it would only
    make the task guesswork. What matters is that it is *data*: the scorer keeps
    its own copy in memory and grades against that, so rewriting ``problem.json``
    inside the sandbox accomplishes nothing.
    """
    keys = (
        "shape",
        "spacing",
        "wavelength",
        "waist_radius",
        "layer_z",
        "output_z",
        "focus_centers",
        "focus_ratios",
        "roi_radius_m",
        "score_eff_target",
        "score_ratio_scale",
        "valid_ratio_mae_max",
        "valid_efficiency_min",
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
            "phases": {
                "shape": spec["phase_shape"],
                "dtype": "float64",
                "units": "radians",
                "description": (
                    "Phase map of each PhaseModulator layer, in the order of layer_z. "
                    "The evaluator builds the optical system from these arrays and runs "
                    "the propagation itself."
                ),
            }
        },
        "optional_arrays": {
            "loss_history": "1-D float array, diagnostics only; never scored.",
        },
    }
    return problem
