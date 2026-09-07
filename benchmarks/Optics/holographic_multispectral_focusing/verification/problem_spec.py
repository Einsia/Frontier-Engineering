"""Scorer-owned problem definition for Holographic H3 (multispectral focusing).

This file used to be ``make_default_spec()`` inside ``baseline/init.py``: the
*candidate* declared the wavelengths, the per-wavelength target coordinates and
the target spectral power ratios, and was then graded against its own
declaration. Moving it here makes the problem fixed for every submission.

It also pins the *design variable* for this task. The old baseline built
``PolychromaticPhaseModulator(Parameter(...))`` with the required refractive
index argument missing, which raises ``TypeError`` on the installed torchoptics
(>=1.0) -- the task could not run at all. The physical variable is now stated
explicitly: a real thickness profile ``t(x, y)`` per layer, of a medium with a
fixed refractive index, which imprints the wavelength-dependent phase

    phi(x, y; lambda) = 2*pi/lambda * (n - 1) * t(x, y)

That dispersion is what makes this a *shared-hardware* problem rather than four
independent single-wavelength holograms.
"""

from __future__ import annotations

import math
from typing import Any

TASK_NAME = "task3_multispectral_focusing"

WAIST_RADIUS = 130e-6

#: Refractive index of the modulator medium (constant, non-dispersive).
REFRACTIVE_INDEX = 1.5

#: Fabricable thickness window, in metres. 10 um spans ~11 full 2*pi wraps at
#: 450 nm, so it does not constrain the design; it does stop a submission from
#: hiding numerical nonsense in an unbounded array.
MAX_THICKNESS_M = 1.0e-5


def make_spec(*, baseline_steps: int = 24, reference_steps: int = 40) -> dict[str, Any]:
    waist = WAIST_RADIUS
    spacing = 10e-6
    wavelengths = [450e-9, 520e-9, 590e-9, 660e-9]

    # Thickness that produces one radian of phase at the reference wavelength.
    # Used to express the optimiser's step size and init spread in metres.
    reference_wavelength = wavelengths[1]
    thickness_per_radian = reference_wavelength / (2.0 * math.pi * (REFRACTIVE_INDEX - 1.0))

    spec: dict[str, Any] = {
        # --- optical model (scorer-owned) ---
        "shape": 72,
        "spacing": spacing,
        "wavelengths": wavelengths,
        "reference_wavelength": reference_wavelength,
        "refractive_index": REFRACTIVE_INDEX,
        "waist_radius": waist,
        "layer_z": [0.0, 0.18, 0.36],
        "output_z": 0.62,
        # --- targets (scorer-owned) ---
        "target_centers": [
            (-2.4 * waist, -0.8 * waist),
            (-0.8 * waist, 1.8 * waist),
            (0.9 * waist, -1.8 * waist),
            (2.3 * waist, 0.8 * waist),
        ],
        "target_spectral_ratios": [0.30, 0.24, 0.26, 0.20],
        "roi_radius_m": 3 * spacing,
        # --- scoring constants (scorer-owned) ---
        "valid_mean_target_efficiency_min": 0.004,
        "valid_mean_crosstalk_max": 0.88,
        "valid_mean_score_min": 0.12,
        "score_eff_target": 0.06,
        "score_spectral_scale": 0.10,
        "better_score_margin": 0.10,
        "better_shape_margin": 0.04,
        # --- budgets ---
        "steps": int(baseline_steps),
        "lr": 0.07 * thickness_per_radian,
        "init_thickness_mean": 2.0e-6,
        "init_thickness_std": 0.2 * thickness_per_radian,
        "num_restarts": 3,
        "xt_weight": 0.9,
        "shape_weight": 0.2,
        "spectral_weight": 0.8,
        "reference_steps": int(reference_steps),
        "reference_lr": 0.045,
        # --- submission contract ---
        "thickness_per_radian": thickness_per_radian,
        "max_thickness_m": MAX_THICKNESS_M,
    }
    spec["n_layers"] = len(spec["layer_z"])
    spec["thickness_shape"] = [spec["n_layers"], spec["shape"], spec["shape"]]
    spec["n_wavelengths"] = len(wavelengths)
    return spec


def candidate_problem(spec: dict[str, Any]) -> dict[str, Any]:
    """The JSON handed to the candidate subprocess -- data only, never authority."""
    keys = (
        "shape",
        "spacing",
        "wavelengths",
        "reference_wavelength",
        "refractive_index",
        "waist_radius",
        "layer_z",
        "output_z",
        "target_centers",
        "target_spectral_ratios",
        "roi_radius_m",
        "score_eff_target",
        "score_spectral_scale",
        "valid_mean_target_efficiency_min",
        "valid_mean_crosstalk_max",
        "valid_mean_score_min",
        "steps",
        "lr",
        "init_thickness_mean",
        "init_thickness_std",
        "num_restarts",
        "xt_weight",
        "shape_weight",
        "spectral_weight",
        "n_layers",
        "n_wavelengths",
        "thickness_shape",
        "thickness_per_radian",
        "max_thickness_m",
    )
    problem = {k: spec[k] for k in keys}
    problem["submission"] = {
        "file": "submission.npz",
        "arrays": {
            "thickness": {
                "shape": spec["thickness_shape"],
                "dtype": "float64",
                "units": "metres",
                "bounds": [0.0, spec["max_thickness_m"]],
                "description": (
                    "Physical thickness profile of each layer, in the order of layer_z. "
                    "A single stack must serve all wavelengths: the evaluator applies "
                    "phi = 2*pi/lambda * (n - 1) * t per wavelength and runs the "
                    "propagation itself."
                ),
            }
        },
        "optional_arrays": {
            "loss_history": "1-D float array, diagnostics only; never scored.",
        },
    }
    return problem
