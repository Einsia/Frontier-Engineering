# EVOLVE-BLOCK-START
"""Baseline solver for Holographic H1: multifocus with target power ratios.

Contract: you receive the problem as data and return *decision variables* only.

    solve(spec) -> np.ndarray of shape (n_layers, shape, shape), float64

Those are the phase maps of the modulator stack, in the order of ``spec["layer_z"]``.
`verification/evaluate.py` builds the optical system from your arrays, runs the
propagation, builds the target and computes the score itself -- so returning a
`system`, an `input_field` or a `target_field` is neither required nor possible.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch.nn import Parameter

import torchoptics
from torchoptics import Field, System
from torchoptics.elements import PhaseModulator
from torchoptics.profiles import gaussian


def build_target_field(spec: dict[str, Any], device: str) -> Field:
    """Local copy of the target used for *training*. The evaluator has its own."""
    shape = int(spec["shape"])
    waist = float(spec["waist_radius"])
    target = torch.zeros((shape, shape), dtype=torch.double, device=device)

    ratios = torch.tensor(spec["focus_ratios"], dtype=torch.double, device=device)
    ratios = ratios / ratios.sum()

    for ratio, center in zip(ratios, spec["focus_centers"]):
        target += torch.sqrt(ratio) * gaussian(shape, waist, offset=tuple(center)).real.to(device)

    return Field(target.to(torch.cdouble), z=float(spec["output_z"])).normalize(1.0)


def build_system(spec: dict[str, Any], device: str) -> System:
    shape = int(spec["shape"])
    layers = [
        PhaseModulator(Parameter(torch.zeros((shape, shape), dtype=torch.double)), z=float(z))
        for z in spec["layer_z"]
    ]
    return System(*layers).to(device)


def solve(spec: dict[str, Any], device: str | None = None, seed: int = 0) -> dict[str, Any]:
    """Optimise the phase stack and return the phase maps.

    Returns a dict with:
      - ``phases``: (n_layers, shape, shape) float64 -- the submission;
      - ``loss_history``: diagnostics only, never scored.
    """
    torch.manual_seed(seed)
    device = device or "cpu"

    torchoptics.set_default_spacing(spec["spacing"])
    torchoptics.set_default_wavelength(spec["wavelength"])

    input_field = Field(
        gaussian(int(spec["shape"]), float(spec["waist_radius"])), z=0
    ).normalize(1.0).to(device)
    target_field = build_target_field(spec, device)
    system = build_system(spec, device)

    optimizer = torch.optim.Adam(system.parameters(), lr=float(spec["lr"]))
    losses: list[float] = []

    for _ in range(int(spec["steps"])):
        optimizer.zero_grad()
        output_field = system.measure_at_z(input_field, z=float(spec["output_z"]))

        overlap = output_field.inner(target_field).abs().square()
        loss = 1.0 - overlap

        loss.backward()
        optimizer.step()
        losses.append(float(loss.item()))

    phases = np.stack(
        [layer.phase.detach().cpu().numpy().astype(np.float64) for layer in system]
    )
    return {"phases": phases, "loss_history": losses}
# EVOLVE-BLOCK-END


# --------------------------------------------------------------------------- #
# Evaluation entry point. `verification/evaluate.py` runs this file as its own
# process in a scratch directory containing exactly one input, `problem.json`,
# and expects exactly one output, `submission.npz`.
#
# Keep this block: without a valid `submission.npz` the run scores as invalid.
# --------------------------------------------------------------------------- #
def _main() -> None:
    import json
    from pathlib import Path

    spec = json.loads(Path("problem.json").read_text(encoding="utf-8"))
    result = solve(spec, device="cpu", seed=0)

    phases = np.asarray(result["phases"], dtype=np.float64)
    np.savez(
        "submission.npz",
        phases=phases,
        loss_history=np.asarray(result.get("loss_history", []), dtype=np.float64),
    )


if __name__ == "__main__":
    _main()
