#!/usr/bin/env python
"""Scorer-owned problem definition for Task 03 (Dammann uniform orders).

The grating period, wavelength, sampling, focal length and the target order
range used to be authored by ``baseline/init.py``. They are authored here now
and shipped to the candidate as read-only input, so the candidate optimizes
against a requirement it cannot restate.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict

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


TASK_NAME = "task03_dammann_uniform_orders"

# diffractio's unit constants: um == 1.0, mm == 1000.0. Spelled out so this
# module does not need diffractio just to state the geometry.
_UM = 1.0
_MM = 1000.0

DEFAULT_CONFIG: Dict[str, Any] = {
    "period_size": 40 * _UM,
    "wavelength": 0.6328 * _UM,
    "period_pixels": 256,
    "num_transitions": 14,
    "num_repetitions": 10,
    "focal": 1 * _MM,
    "lens_radius": 1 * _MM,
    "order_min": -3,
    "order_max": 3,
    "order_window_halfwidth_px": 3,
}


def build_problem(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    x_period = np.linspace(-cfg["period_size"] / 2, cfg["period_size"] / 2, cfg["period_pixels"])

    return {
        "cfg": cfg,
        "x_period": x_period,
    }


def transition_bounds(problem: Dict[str, Any]) -> tuple[float, float]:
    """Inclusive bounds a transition position must fall inside."""
    half = float(problem["cfg"]["period_size"]) / 2.0
    return -half, half


def baseline_transitions(problem: Dict[str, Any]) -> np.ndarray:
    """The naive reference decision vector (also the shipped baseline)."""
    cfg = problem["cfg"]
    return np.linspace(
        -0.45 * cfg["period_size"], 0.45 * cfg["period_size"], int(cfg["num_transitions"])
    )


def candidate_inputs(problem: Dict[str, Any]) -> Dict[str, bytes]:
    """Files staged read-only into the candidate's throwaway working directory."""
    cfg = problem["cfg"]
    lo, hi = transition_bounds(problem)
    meta = {
        "task": TASK_NAME,
        "cfg": {k: (float(v) if isinstance(v, float) else v) for k, v in cfg.items()},
        "decision_variable": {
            "file": "submission.json",
            "key": "transitions",
            "kind": "binary-phase transition positions in one period (um)",
            "length": int(cfg["num_transitions"]),
            "bounds": [lo, hi],
            "constraint": "strictly increasing, every entry inside bounds, all finite",
        },
        "arrays_file": "problem.npz",
        "arrays": ["x_period"],
        "note": (
            "Return only the transition vector. The grating, the "
            "Rayleigh-Sommerfeld propagation and every order metric "
            "(cv_orders, efficiency, min_to_max) are recomputed by the scorer; "
            "any other key in submission.json is discarded."
        ),
    }
    arrays = common.pack_npz(x_period=problem["x_period"])
    return {"problem.json": common.pack_json(meta), "problem.npz": arrays}
