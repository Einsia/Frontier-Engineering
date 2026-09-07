#!/usr/bin/env python
# EVOLVE-BLOCK-START
"""Baseline solver for Task 04: large-scale weighted spot-array Fourier DOE.

Contract
--------
The scorer runs this file in its own process, in a throwaway directory that
already contains ``problem.npz`` (``x``, ``y``, ``spots``, ``weights``,
``aperture_amp``) and ``problem.json``. Write the decision variable -- and only
the decision variable -- to ``submission.json``::

    {"phase": [[...128 floats...], ...]}   # 128 rows, radians

The forward model, the metrics and the score all live in ``verification/`` and
are recomputed there from this phase map. Extra keys in submission.json are
discarded.
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


def solve(problem: Dict[str, Any]) -> np.ndarray:
    """Direct plane-wave superposition phase (no iterative balancing)."""
    x = problem["x"]
    y = problem["y"]
    n = len(x)
    c = (n - 1) / 2.0
    X, Y = np.meshgrid(x, y)

    U = np.zeros_like(X, dtype=complex)
    for (sx, sy), w in zip(problem["spots"], problem["weights"]):
        fx = (sx - c) / n
        fy = (sy - c) / n
        U += np.sqrt(w) * np.exp(-1j * 2.0 * np.pi * (fx * (X - c) + fy * (Y - c)))

    return np.angle(U)


def main() -> None:
    problem = load_problem()
    phase = np.asarray(solve(problem), dtype=float)
    Path("submission.json").write_text(
        json.dumps({"phase": phase.tolist()}), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
