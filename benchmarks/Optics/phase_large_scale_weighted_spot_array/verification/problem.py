#!/usr/bin/env python
"""Scorer-owned problem definition for Task 04 (large-scale weighted spot array).

The aperture, the 8x8 spot grid and the weight vector used to be authored by
``baseline/init.py`` -- the candidate stated the requirement it was then graded
against. They are authored here now and shipped to the candidate read-only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np


def _load_common():
    """Import the shared scorer library from outside the benchmark sandbox."""
    roots: list[Path] = []
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())
    for parent in Path(__file__).resolve().parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            roots.append(parent)
    for root in roots:
        shared = root / "benchmarks" / "Optics" / "_shared"
        if (shared / "phase_common.py").is_file():
            if str(shared) not in sys.path:
                sys.path.insert(0, str(shared))
            import phase_common  # noqa: PLC0415

            return phase_common
    raise RuntimeError(
        "could not locate benchmarks/Optics/_shared/phase_common.py; "
        "set FRONTIER_ENGINEERING_ROOT to the repo root"
    )


common = _load_common()


TASK_NAME = "task04_large_scale_spot_array"

DEFAULT_CONFIG: Dict[str, Any] = {
    "slm_pixels": 128,
    "aperture_radius_px": 58,
    "grid_rows": 8,
    "grid_cols": 8,
    "spot_x_min": 20.0,
    "spot_x_max": 108.0,
    "spot_y_min": 20.0,
    "spot_y_max": 108.0,
}


def build_spots_and_weights(cfg: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    xs = np.linspace(float(cfg["spot_x_min"]), float(cfg["spot_x_max"]), int(cfg["grid_cols"]))
    ys = np.linspace(float(cfg["spot_y_min"]), float(cfg["spot_y_max"]), int(cfg["grid_rows"]))

    spots = []
    weights = []
    for j, yy in enumerate(ys):
        for i, xx in enumerate(xs):
            # Deliberately non-uniform engineering requirement.
            w = 0.3 + 0.7 * (((i + j) % 5) + 1) / 5.0
            spots.append([xx, yy])
            weights.append(w)

    weights_arr = np.asarray(weights, dtype=float)
    weights_arr = weights_arr / np.sum(weights_arr)

    return np.asarray(spots, dtype=float), weights_arr


def build_problem(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    n = int(cfg["slm_pixels"])
    x = np.arange(n, dtype=float)
    y = np.arange(n, dtype=float)

    spots, weights = build_spots_and_weights(cfg)
    aperture_amp = common.circular_aperture(n, float(cfg["aperture_radius_px"]))

    return {
        "cfg": cfg,
        "x": x,
        "y": y,
        "spots": spots,
        "weights": weights,
        "aperture_amp": aperture_amp,
    }


def candidate_inputs(problem: Dict[str, Any]) -> Dict[str, bytes]:
    """Files staged read-only into the candidate's throwaway working directory."""
    cfg = problem["cfg"]
    meta = {
        "task": TASK_NAME,
        "cfg": {k: (float(v) if isinstance(v, float) else v) for k, v in cfg.items()},
        "decision_variable": {
            "file": "submission.json",
            "key": "phase",
            "kind": "phase map in radians",
            "shape": [int(cfg["slm_pixels"]), int(cfg["slm_pixels"])],
            "abs_max": common.PHASE_ABS_MAX,
        },
        "arrays_file": "problem.npz",
        "arrays": ["x", "y", "spots", "weights", "aperture_amp"],
        "note": (
            "Return only the phase map. Any other key in submission.json is "
            "discarded; the scorer recomputes the forward model and every metric."
        ),
    }
    arrays = common.pack_npz(
        x=problem["x"],
        y=problem["y"],
        spots=problem["spots"],
        weights=problem["weights"],
        aperture_amp=problem["aperture_amp"],
    )
    return {"problem.json": common.pack_json(meta), "problem.npz": arrays}
