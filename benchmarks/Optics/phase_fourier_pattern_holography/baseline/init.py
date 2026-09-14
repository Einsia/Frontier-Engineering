#!/usr/bin/env python
# EVOLVE-BLOCK-START
"""Baseline solver for Task 02: hard Fourier pattern holography.

Contract
--------
The scorer runs this file in its own process, in a throwaway directory that
already contains ``problem.npz`` (``x``, ``y``, ``aperture_amp``, ``target_amp``)
and ``problem.json``. Write the decision variable -- and only the decision
variable -- to ``submission.json``::

    {"phase": [[...128 floats...], ...]}   # 128 rows, radians

``target_amp`` is fixed by the scorer; propagation, NMSE, energy-in-target,
dark suppression and the score are recomputed in ``verification/`` from this
phase map. Extra keys in submission.json are discarded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np


def load_problem(directory: Path | None = None) -> Dict[str, Any]:
    """Read the scorer-supplied problem definition."""
    base = Path(directory) if directory is not None else Path.cwd()
    meta = json.loads((base / "problem.json").read_text(encoding="utf-8"))
    with np.load(base / "problem.npz") as data:
        arrays = {key: np.asarray(data[key]) for key in data.files}
    return {"cfg": meta["cfg"], **arrays}


def solve(problem: Dict[str, Any], seed: int | None = None) -> np.ndarray:
    """One-shot inverse FFT baseline with random target phase."""
    seed_value = int(problem["cfg"]["seed"] if seed is None else seed)
    rng = np.random.default_rng(seed_value)

    target_amp = problem["target_amp"]
    Uz = target_amp * np.exp(1j * 2.0 * np.pi * rng.random(target_amp.shape))
    back = np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(Uz), norm="ortho"))
    return np.angle(back)


def main() -> None:
    problem = load_problem()
    phase = np.asarray(solve(problem), dtype=float)
    Path("submission.json").write_text(
        json.dumps({"phase": phase.tolist()}), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
