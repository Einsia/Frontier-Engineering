# EVOLVE-BLOCK-START
"""Baseline solver for Holographic H3: multi-wavelength focusing/splitting.

Contract: you receive the problem as data and return *decision variables* only.

    solve(spec) -> {"thickness": np.ndarray (n_layers, shape, shape) float64, ...}

The decision variable is the physical thickness profile of each layer, in metres,
bounded to ``[0, spec["max_thickness_m"]]``. One shared stack must serve all four
wavelengths: the evaluator applies

    phi(x, y; lambda) = 2*pi/lambda * (n - 1) * t(x, y)

with ``n = spec["refractive_index"]``, builds the input fields, runs the
propagation and computes the score itself -- so returning a `system` or
`input_fields` is neither required nor possible.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import torch
from torch.nn import Parameter

import torchoptics
from torchoptics import Field, System
from torchoptics.elements import PolychromaticPhaseModulator
from torchoptics.profiles import gaussian


def build_system(spec: dict[str, Any], device: str) -> System:
    """Dispersive stack: one thickness map per layer, shared by all wavelengths."""
    shape = int(spec["shape"])
    mean = float(spec["init_thickness_mean"])
    std = float(spec["init_thickness_std"])
    layers = [
        PolychromaticPhaseModulator(
            Parameter(mean + std * torch.randn((shape, shape), dtype=torch.double)),
            float(spec["refractive_index"]),
            z=float(z),
        )
        for z in spec["layer_z"]
    ]
    return System(*layers).to(device)


def make_input_fields(spec: dict[str, Any], device: str) -> list[Field]:
    fields = []
    for wl in spec["wavelengths"]:
        field = Field(
            gaussian(int(spec["shape"]), float(spec["waist_radius"])),
            wavelength=float(wl),
            z=0,
        ).normalize(1.0)
        fields.append(field.to(device))
    return fields


def roi_power(field: Field, center, radius: float) -> torch.Tensor:
    x, y = field.meshgrid()
    intensity = field.intensity()
    mask = ((x - center[0]) ** 2 + (y - center[1]) ** 2) <= radius**2
    return (intensity * mask.to(intensity.dtype)).sum()


def all_designated_powers(field: Field, centers, radius: float) -> torch.Tensor:
    return torch.stack([roi_power(field, center, radius) for center in centers])


def cosine_similarity(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    a_flat = a.flatten()
    b_flat = b.flatten()
    return torch.dot(a_flat, b_flat) / (torch.norm(a_flat) * torch.norm(b_flat) + 1e-12)


def make_target_maps(spec: dict[str, Any], device: str) -> list[torch.Tensor]:
    target_maps: list[torch.Tensor] = []
    for center in spec["target_centers"]:
        target_map = gaussian(
            int(spec["shape"]), float(spec["waist_radius"]), offset=tuple(center)
        ).real.to(device)
        target_maps.append(target_map / (target_map.sum() + 1e-12))
    return target_maps


def _clamp_thickness(system: System, spec: dict[str, Any]) -> None:
    """Keep every layer inside the fabricable thickness window."""
    hi = float(spec["max_thickness_m"])
    with torch.no_grad():
        for layer in system:
            layer.thickness.clamp_(0.0, hi)


def _score_solution(system, input_fields, target_maps, target_spectral, spec, roi_radius) -> float:
    """Local scoring used only to pick the best restart. The evaluator has its own."""
    target_powers = []
    effs, xts, shapes = [], [], []

    with torch.no_grad():
        for idx, (field, target_map) in enumerate(zip(input_fields, target_maps)):
            out = system.measure_at_z(field, z=float(spec["output_z"]))
            all_designated = all_designated_powers(out, spec["target_centers"], roi_radius)
            target_power = all_designated[idx]
            target_powers.append(target_power)

            total_power = out.intensity().sum() + 1e-12
            designated_total = all_designated.sum() + 1e-12
            pred_norm = out.intensity() / total_power

            effs.append(float((target_power / total_power).item()))
            xts.append(float(((designated_total - target_power) / designated_total).item()))
            shapes.append(float(cosine_similarity(pred_norm, target_map).item()))

    pred_spectral = torch.stack(target_powers)
    pred_spectral = pred_spectral / (pred_spectral.sum() + 1e-12)
    spectral_ratio_mae = float(torch.mean(torch.abs(pred_spectral - target_spectral)).item())

    mean_eff = sum(effs) / len(effs)
    mean_xt = sum(xts) / len(xts)
    mean_shape = sum(shapes) / len(shapes)

    efficiency_score = min(1.0, max(0.0, mean_eff / float(spec["score_eff_target"])))
    isolation_score = min(1.0, max(0.0, 1.0 - mean_xt))
    spectral_score = math.exp(-spectral_ratio_mae / float(spec["score_spectral_scale"]))
    score = (
        (efficiency_score**0.45)
        * (isolation_score**0.25)
        * (spectral_score**0.20)
        * (max(mean_shape, 0.0) ** 0.10)
    )
    return float(min(1.0, max(0.0, score)))


def solve(spec: dict[str, Any], device: str | None = None, seed: int = 0) -> dict[str, Any]:
    device = device or "cpu"
    torchoptics.set_default_spacing(spec["spacing"])
    torchoptics.set_default_wavelength(spec["reference_wavelength"])

    roi_radius = float(spec["roi_radius_m"])
    xt_weight = float(spec["xt_weight"])
    shape_weight = float(spec["shape_weight"])
    spectral_weight = float(spec["spectral_weight"])
    num_restarts = max(int(spec["num_restarts"]), 1)

    input_fields = make_input_fields(spec, device)
    target_maps = make_target_maps(spec, device)
    target_spectral = torch.tensor(spec["target_spectral_ratios"], dtype=torch.double, device=device)
    target_spectral = target_spectral / target_spectral.sum()

    best_system: System | None = None
    best_losses: list[float] = []
    best_score = float("-inf")

    # Try a few fixed restarts because shared-mask optimization is sensitive to initialization.
    for restart_idx in range(num_restarts):
        torch.manual_seed(seed + restart_idx)
        system = build_system(spec, device)
        optimizer = torch.optim.Adam(system.parameters(), lr=float(spec["lr"]))
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=max(int(spec["steps"]), 1)
        )
        losses: list[float] = []

        for _ in range(int(spec["steps"])):
            optimizer.zero_grad()

            target_powers = []
            per_wavelength_losses = []
            for idx, (field, target_map) in enumerate(zip(input_fields, target_maps)):
                out = system.measure_at_z(field, z=float(spec["output_z"]))
                all_designated = all_designated_powers(out, spec["target_centers"], roi_radius)
                target_power = all_designated[idx]
                target_powers.append(target_power)
                total_power = out.intensity().sum() + 1e-12
                other_designated_power = all_designated.sum() - target_power
                pred_norm = out.intensity() / total_power
                shape_cosine = cosine_similarity(pred_norm, target_map)
                per_wavelength_losses.append(
                    (1.0 - target_power / total_power)
                    + xt_weight * (other_designated_power / total_power)
                    + shape_weight * (1.0 - shape_cosine)
                )

            pred_spectral = torch.stack(target_powers)
            pred_spectral = pred_spectral / (pred_spectral.sum() + 1e-12)
            spectral_loss = torch.mean(torch.abs(pred_spectral - target_spectral))
            loss = torch.stack(per_wavelength_losses).mean() + spectral_weight * spectral_loss
            loss.backward()
            optimizer.step()
            scheduler.step()
            _clamp_thickness(system, spec)

            losses.append(float(loss.item()))

        score = _score_solution(
            system, input_fields, target_maps, target_spectral, spec, roi_radius
        )
        if score > best_score:
            best_score = score
            best_system = system
            best_losses = losses

    if best_system is None:
        raise RuntimeError("Failed to optimize a baseline optical system.")

    thickness = np.stack(
        [layer.thickness.detach().cpu().numpy().astype(np.float64) for layer in best_system]
    )
    return {"thickness": thickness, "loss_history": best_losses}
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

    thickness = np.clip(
        np.asarray(result["thickness"], dtype=np.float64), 0.0, float(spec["max_thickness_m"])
    )
    np.savez(
        "submission.npz",
        thickness=thickness,
        loss_history=np.asarray(result.get("loss_history", []), dtype=np.float64),
    )


if __name__ == "__main__":
    _main()
