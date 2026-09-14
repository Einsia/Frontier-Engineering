#!/usr/bin/env python
# EVOLVE-BLOCK-START
"""Baseline solver for Task 03: Dammann-like 1D binary phase grating transitions.

Contract
--------
The scorer runs this file in its own process, in a throwaway directory that
already contains ``problem.npz`` (``x_period``) and ``problem.json`` (the
grating geometry and the target order range). Write the decision variable --
and only the decision variable -- to ``submission.json``::

    {"transitions": [t0, t1, ..., t13]}   # micrometres, strictly increasing

Every entry must be finite and inside ``[-period_size/2, +period_size/2]``, and
the vector must be strictly increasing; the scorer rejects the run otherwise.
The grating construction, the Rayleigh-Sommerfeld propagation and all order
metrics (``cv_orders``, ``efficiency``, ``min_to_max``) are recomputed in
``verification/``. Extra keys in submission.json are discarded.
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
    """Naive evenly-spaced transitions inside a fixed margin."""
    cfg = problem["cfg"]
    return np.linspace(
        -0.45 * cfg["period_size"],
        0.45 * cfg["period_size"],
        int(cfg["num_transitions"]),
    )


def main() -> None:
    problem = load_problem()
    transitions = np.asarray(solve(problem), dtype=float)
    Path("submission.json").write_text(
        json.dumps({"transitions": transitions.tolist()}), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
