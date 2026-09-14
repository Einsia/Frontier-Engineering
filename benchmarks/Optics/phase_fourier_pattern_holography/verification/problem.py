#!/usr/bin/env python
"""Scorer-owned problem definition for Fourier pattern holography.

The target pattern and aperture are fixed here and supplied to the candidate.
Candidates return a phase map to be evaluated against that target.
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


TASK_NAME = "task02_fourier_pattern_holography"

DEFAULT_CONFIG: Dict[str, Any] = {
    "slm_pixels": 128,
    "aperture_radius_px": 56,
    "seed": 0,
}


def build_target_pattern(n: int) -> np.ndarray:
    y, x = np.indices((n, n))
    c = (n - 1) / 2.0

    target = np.zeros((n, n), dtype=float)

    xs = np.linspace(18, 110, 8)
    ys = np.linspace(18, 110, 8)
    for j, yy in enumerate(ys):
        for i, xx in enumerate(xs):
            amp = 0.2 + 0.8 * (0.5 + 0.5 * np.sin(0.7 * i + 0.9 * j))
            if (i + j) % 2 == 0:
                amp *= 0.4
            target += amp * np.exp(-((x - xx) ** 2 + (y - yy) ** 2) / (2.0 * 0.9**2))

    for xx in range(20, 108):
        yy = int(64 + 18 * np.sin((xx - 20) / 13.0))
        target[max(0, yy - 1):min(n, yy + 2), max(0, xx - 1):min(n, xx + 2)] += 0.35

    dark_zone = (np.abs(x - c) < 4) & (np.abs(y - c) < 45)
    target[dark_zone] = 0.0

    target = np.clip(target, 0.0, None)
    target = target / (target.max() + 1e-12)
    return target


def build_problem(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    n = int(cfg["slm_pixels"])
    x = np.arange(n, dtype=float)
    y = np.arange(n, dtype=float)

    aperture_amp = common.circular_aperture(n, float(cfg["aperture_radius_px"]))
    target_amp = build_target_pattern(n)

    return {
        "cfg": cfg,
        "x": x,
        "y": y,
        "aperture_amp": aperture_amp,
        "target_amp": target_amp,
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
        "arrays": ["x", "y", "aperture_amp", "target_amp"],
        "note": (
            "target_amp is fixed by the scorer. Return only the phase map; any "
            "other key in submission.json is discarded and every metric is "
            "recomputed from this phase against this target."
        ),
    }
    arrays = common.pack_npz(
        x=problem["x"],
        y=problem["y"],
        aperture_amp=problem["aperture_amp"],
        target_amp=problem["target_amp"],
    )
    return {"problem.json": common.pack_json(meta), "problem.npz": arrays}
