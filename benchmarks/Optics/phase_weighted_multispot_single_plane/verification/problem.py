#!/usr/bin/env python
"""Scorer-owned problem definition for Task 01 (hard weighted multi-spot).

Everything here used to live in ``baseline/init.py`` -- the file the candidate
is allowed to rewrite. That meant the candidate authored its own aperture, its
own spot grid and its own target weights, and the validator then graded the
candidate against the candidate's own statement of the problem.

The definition now lives on the scoring side and is shipped *to* the candidate
as read-only input files. The candidate's only output is a phase map.
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


TASK_NAME = "task01_weighted_multispot_single_plane"

DEFAULT_CONFIG: Dict[str, Any] = {
    "slm_pixels": 128,
    "aperture_radius_px": 56,
    "grid_rows": 7,
    "grid_cols": 7,
    "spot_x_min": 18.0,
    "spot_x_max": 110.0,
    "spot_y_min": 18.0,
    "spot_y_max": 110.0,
}


def build_spots_and_weights(cfg: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    xs = np.linspace(float(cfg["spot_x_min"]), float(cfg["spot_x_max"]), int(cfg["grid_cols"]))
    ys = np.linspace(float(cfg["spot_y_min"]), float(cfg["spot_y_max"]), int(cfg["grid_rows"]))

    spots = []
    weights = []
    for j, yy in enumerate(ys):
        for i, xx in enumerate(xs):
            # Hard nonuniform target distribution to increase optimization difficulty.
            w = 0.12 + 0.88 * (0.5 + 0.5 * np.sin(0.9 * i + 1.25 * j))
            if (i + j) % 2 == 0:
                w *= 0.25
            if (i * j) % 3 == 0:
                w *= 0.60
            spots.append([xx, yy])
            weights.append(w)

    weights_arr = np.asarray(weights, dtype=float)
    weights_arr = weights_arr / (weights_arr.sum() + 1e-12)
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
