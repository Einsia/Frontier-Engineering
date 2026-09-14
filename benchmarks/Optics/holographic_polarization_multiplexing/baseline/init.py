# EVOLVE-BLOCK-START
"""Baseline solver for Holographic H4: polarization-multiplexed focusing.

Contract: you receive the problem as data and return *decision variables* only.

    solve(spec) -> {"phase_x": (n_layers, shape, shape),
                    "phase_y": (n_layers, shape, shape), ...}

Those are the diagonal Jones phases of each layer. `verification/evaluate.py`
builds both polarised input fields, runs the propagation and modulation, builds
both target maps and computes the score itself -- so returning `output_field_x` /
`target_map_x` (as the old contract did) is neither required nor possible.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch.nn import Parameter

import torchoptics
from torchoptics import Field
from torchoptics.profiles import gaussian


def build_input_fields(spec: dict[str, Any], device: str) -> tuple[Field, Field]:
    shape = int(spec["shape"])
    base = gaussian(shape, float(spec["waist_radius"]))  # real-valued profile

    data_x = torch.zeros((3, shape, shape), dtype=torch.cdouble)
    data_y = torch.zeros((3, shape, shape), dtype=torch.cdouble)
    data_x[0] = base.to(torch.cdouble)
    data_y[1] = base.to(torch.cdouble)

    field_x = Field(data_x, wavelength=float(spec["wavelength"]), z=0).normalize(1.0).to(device)
    field_y = Field(data_y, wavelength=float(spec["wavelength"]), z=0).normalize(1.0).to(device)
    return field_x, field_y


def build_target_map(shape: int, waist: float, centers, ratios, device: str) -> torch.Tensor:
    """Local copy of a target used for *training*. The evaluator has its own."""
    target = torch.zeros((shape, shape), dtype=torch.double, device=device)
    ratio_t = torch.tensor(list(ratios), dtype=torch.double, device=device)
    ratio_t = ratio_t / ratio_t.sum()
    for ratio, center in zip(ratio_t, centers):
        target += ratio * gaussian(shape, waist, offset=tuple(center)).real.to(device)
    return target / (target.sum() + 1e-12)


def jones_from_phase(phase_x: torch.Tensor, phase_y: torch.Tensor) -> torch.Tensor:
    shape = phase_x.shape
    jones = torch.zeros((3, 3, shape[0], shape[1]), dtype=torch.cdouble, device=phase_x.device)
    jones[0, 0] = torch.exp(1j * phase_x)
    jones[1, 1] = torch.exp(1j * phase_y)
    jones[2, 2] = 1.0 + 0j
    return jones


def forward(field: Field, spec: dict[str, Any], phase_x_layers, phase_y_layers) -> Field:
    out = field
    for z, phase_x, phase_y in zip(spec["layer_z"], phase_x_layers, phase_y_layers):
        out = out.propagate_to_z(float(z))
        out = out.polarized_modulate(jones_from_phase(phase_x, phase_y))
    return out.propagate_to_z(float(spec["output_z"]))


def solve(spec: dict[str, Any], device: str | None = None, seed: int = 0) -> dict[str, Any]:
    torch.manual_seed(seed)
    device = device or "cpu"

    torchoptics.set_default_spacing(spec["spacing"])
    torchoptics.set_default_wavelength(spec["wavelength"])

    shape = int(spec["shape"])
    field_x, field_y = build_input_fields(spec, device)

    target_x = build_target_map(
        shape, float(spec["waist_radius"]), spec["pattern_x_centers"], spec["pattern_x_ratios"], device
    )
    target_y = build_target_map(
        shape, float(spec["waist_radius"]), spec["pattern_y_centers"], spec["pattern_y_ratios"], device
    )

    phase_x_layers = [
        Parameter(torch.zeros((shape, shape), dtype=torch.double, device=device))
        for _ in spec["layer_z"]
    ]
    phase_y_layers = [
        Parameter(torch.zeros((shape, shape), dtype=torch.double, device=device))
        for _ in spec["layer_z"]
    ]

    optimizer = torch.optim.Adam([*phase_x_layers, *phase_y_layers], lr=float(spec["lr"]))
    losses: list[float] = []

    for _ in range(int(spec["steps"])):
        optimizer.zero_grad()

        out_x = forward(field_x, spec, phase_x_layers, phase_y_layers)
        out_y = forward(field_y, spec, phase_x_layers, phase_y_layers)

        map_x = out_x.intensity().sum(dim=-3)
        map_y = out_y.intensity().sum(dim=-3)

        map_x = map_x / (map_x.sum() + 1e-12)
        map_y = map_y / (map_y.sum() + 1e-12)

        loss = torch.mean((map_x - target_x) ** 2) + torch.mean((map_y - target_y) ** 2)
        loss.backward()
        optimizer.step()

        losses.append(float(loss.item()))

    return {
        "phase_x": np.stack([p.detach().cpu().numpy().astype(np.float64) for p in phase_x_layers]),
        "phase_y": np.stack([p.detach().cpu().numpy().astype(np.float64) for p in phase_y_layers]),
        "loss_history": losses,
    }
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
        phase_x=np.asarray(result["phase_x"], dtype=np.float64),
        phase_y=np.asarray(result["phase_y"], dtype=np.float64),
        loss_history=np.asarray(result.get("loss_history", []), dtype=np.float64),
    )


if __name__ == "__main__":
    _main()
