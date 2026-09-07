# EVOLVE-BLOCK-START
"""Baseline solver for Holographic H2: multi-plane focusing.

Contract: you receive the problem as data and return *decision variables* only.

    solve(spec) -> {"phases": np.ndarray (n_layers, shape, shape) float64, ...}

One shared phase stack must serve every observation plane in ``spec["planes"]``.
`verification/evaluate.py` builds the optical system from your arrays,
propagates to each plane, builds each target and computes the score itself -- so
returning a `system` / `input_field` / `target_fields` is neither required nor
possible.
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


def build_system(spec: dict[str, Any], device: str) -> System:
    shape = int(spec["shape"])
    layers = [
        PhaseModulator(Parameter(torch.zeros((shape, shape), dtype=torch.double)), z=float(z))
        for z in spec["layer_z"]
    ]
    return System(*layers).to(device)


def build_target_field_for_plane(spec: dict[str, Any], plane_cfg: dict[str, Any], device: str) -> Field:
    """Local copy of a plane's target used for *training*. The evaluator has its own."""
    shape = int(spec["shape"])
    waist = float(spec["waist_radius"])

    target = torch.zeros((shape, shape), dtype=torch.double, device=device)
    ratios = torch.tensor(plane_cfg["ratios"], dtype=torch.double, device=device)
    ratios = ratios / ratios.sum()

    for ratio, center in zip(ratios, plane_cfg["centers"]):
        target += torch.sqrt(ratio) * gaussian(shape, waist, offset=tuple(center)).real.to(device)

    return Field(target.to(torch.cdouble), z=float(plane_cfg["z"])).normalize(1.0)


def solve(spec: dict[str, Any], device: str | None = None, seed: int = 0) -> dict[str, Any]:
    torch.manual_seed(seed)
    device = device or "cpu"

    torchoptics.set_default_spacing(spec["spacing"])
    torchoptics.set_default_wavelength(spec["wavelength"])

    input_field = Field(
        gaussian(int(spec["shape"]), float(spec["waist_radius"])), z=0
    ).normalize(1.0).to(device)
    system = build_system(spec, device)
    target_fields = [build_target_field_for_plane(spec, p, device) for p in spec["planes"]]

    optimizer = torch.optim.Adam(system.parameters(), lr=float(spec["lr"]))
    losses: list[float] = []

    for _ in range(int(spec["steps"])):
        optimizer.zero_grad()
        plane_losses = []
        for plane_cfg, target_field in zip(spec["planes"], target_fields):
            output = system.measure_at_z(input_field, z=float(plane_cfg["z"]))
            plane_losses.append(1.0 - output.inner(target_field).abs().square())

        loss = torch.stack(plane_losses).mean()
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

    np.savez(
        "submission.npz",
        phases=np.asarray(result["phases"], dtype=np.float64),
        loss_history=np.asarray(result.get("loss_history", []), dtype=np.float64),
    )


if __name__ == "__main__":
    _main()
