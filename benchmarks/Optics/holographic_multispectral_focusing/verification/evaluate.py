"""Evaluator for holographic multispectral focusing.

The scorer loads the problem from ``verification/problem_spec.py``. The
candidate runs in a subprocess and returns thickness maps for each layer
in ``submission.npz``. The scorer validates those arrays and constructs
the dispersive system, input fields at each wavelength and metrics.

The reference uses separate phase masks for each wavelength, which is a larger
design space than the candidate's shared dispersive stack. This reference
choice is recorded in ``summary.json`` as ``reference.design_space``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
TASK_DIR = THIS_DIR.parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))


def _find_repo_root() -> Path:
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    raise RuntimeError("could not locate repo root for holographic_multispectral_focusing")


_REPO = _find_repo_root()
if str(_REPO / "benchmarks" / "_shared") not in sys.path:
    sys.path.insert(0, str(_REPO / "benchmarks" / "_shared"))

# Invariant 1: every scoring dependency is resident before the candidate runs.
import numpy as np  # noqa: E402
import torch  # noqa: E402

import optics_holographic as shared  # noqa: E402
import problem_spec  # noqa: E402
import reference_solver  # noqa: E402

TASK_NAME = problem_spec.TASK_NAME


# --------------------------------------------------------------------------- #
# Scorer-owned forward models.
# --------------------------------------------------------------------------- #
def _input_fields(spec: dict[str, Any], device: str) -> list:
    return [
        shared.gaussian_input_field(
            spec["shape"], spec["waist_radius"], device=device, wavelength=float(wl)
        )
        for wl in spec["wavelengths"]
    ]


def _outputs_shared_stack(thickness: np.ndarray, spec: dict[str, Any], device: str, fields) -> list:
    """Candidate design space: ONE dispersive thickness stack for all wavelengths."""
    system = shared.build_thickness_system(
        thickness, spec["layer_z"], float(spec["refractive_index"]), device
    )
    with torch.no_grad():
        return [system.measure_at_z(f, z=float(spec["output_z"])) for f in fields]


def _outputs_per_wavelength(phases: np.ndarray, spec: dict[str, Any], device: str, fields) -> list:
    """Oracle-only relaxation: an independent phase mask per wavelength at z=0."""
    outs = []
    with torch.no_grad():
        for idx, field in enumerate(fields):
            phase = torch.as_tensor(np.asarray(phases[idx]), dtype=torch.double, device=device)
            outs.append(
                field.modulate(torch.exp(1j * phase)).propagate_to_z(float(spec["output_z"]))
            )
    return outs


# --------------------------------------------------------------------------- #
# Scorer-owned metrics.
# --------------------------------------------------------------------------- #
def _score_outputs(outputs, spec: dict[str, Any], device: str) -> dict[str, Any]:
    roi_radius = float(spec["roi_radius_m"])

    per_wavelength = []
    target_powers = []

    for idx, out in enumerate(outputs):
        all_designated = shared.roi_powers(out, spec["target_centers"], roi_radius)
        target_power = all_designated[idx]
        target_powers.append(target_power)

        designated_total = all_designated.sum() + 1e-12
        intensity = out.intensity()
        total_power = intensity.sum() + 1e-12

        target_eff = (target_power / total_power).item()
        crosstalk = ((designated_total - target_power) / designated_total).item()
        pred_norm = intensity / total_power
        target_norm = shared.normalized_gaussian_map(
            spec["shape"], spec["waist_radius"], spec["target_centers"][idx], device
        )
        shape_cosine = shared.cosine_similarity(pred_norm, target_norm)
        shape_l1 = float(torch.mean(torch.abs(pred_norm - target_norm)).item())

        per_wavelength.append(
            {
                "wavelength": spec["wavelengths"][idx],
                "target_efficiency": target_eff,
                "designated_crosstalk": crosstalk,
                "shape_cosine": shape_cosine,
                "shape_l1": shape_l1,
                "intensity": intensity.detach().cpu(),
            }
        )

    target_powers_t = torch.stack(target_powers)
    pred_spectral = target_powers_t / (target_powers_t.sum() + 1e-12)
    target_spectral = torch.tensor(
        spec["target_spectral_ratios"], dtype=torch.double, device=pred_spectral.device
    )
    target_spectral = target_spectral / target_spectral.sum()

    spectral_ratio_mae = torch.mean(torch.abs(pred_spectral - target_spectral)).item()
    n = len(per_wavelength)
    mean_eff = sum(x["target_efficiency"] for x in per_wavelength) / n
    mean_xt = sum(x["designated_crosstalk"] for x in per_wavelength) / n
    mean_shape_cosine = sum(x["shape_cosine"] for x in per_wavelength) / n

    efficiency_score = shared.clip01(mean_eff / float(spec["score_eff_target"]))
    isolation_score = shared.clip01(1.0 - mean_xt)
    spectral_score = math.exp(-spectral_ratio_mae / float(spec["score_spectral_scale"]))
    score = (
        (efficiency_score**0.45)
        * (isolation_score**0.25)
        * (max(spectral_score, 0.0) ** 0.20)
        * (max(mean_shape_cosine, 0.0) ** 0.10)
    )

    return {
        "per_wavelength": per_wavelength,
        "mean_target_efficiency": mean_eff,
        "mean_crosstalk": mean_xt,
        "mean_shape_cosine": mean_shape_cosine,
        "efficiency_score": efficiency_score,
        "isolation_score": isolation_score,
        "spectral_score": spectral_score,
        "spectral_ratio_mae": spectral_ratio_mae,
        "pred_spectral_ratios": pred_spectral.detach().cpu().tolist(),
        "target_spectral_ratios": target_spectral.detach().cpu().tolist(),
        "mean_score": shared.clip01(score),
    }


# --------------------------------------------------------------------------- #
# Reporting.
# --------------------------------------------------------------------------- #
def _plot_outputs(spec, baseline_eval, reference_eval, baseline_losses, ref_losses, device, save_dir: Path):
    plt = shared.use_agg_matplotlib()
    _norm = shared.norm_for_plot
    n = len(spec["wavelengths"])

    fig, axes = plt.subplots(n, 3, figsize=(10, 3.2 * n), squeeze=False)
    for i, wl in enumerate(spec["wavelengths"]):
        target_map = shared.normalized_gaussian_map(
            spec["shape"], spec["waist_radius"], spec["target_centers"][i], device
        ).detach().cpu()
        axes[i][0].imshow(_norm(target_map), cmap="inferno")
        axes[i][0].set_title(f"{wl*1e9:.0f}nm Target")
        axes[i][1].imshow(_norm(baseline_eval["per_wavelength"][i]["intensity"]), cmap="inferno")
        axes[i][1].set_title("Candidate")
        axes[i][2].imshow(_norm(reference_eval["per_wavelength"][i]["intensity"]), cmap="inferno")
        axes[i][2].set_title("Reference")
        for j in range(3):
            axes[i][j].axis("off")

    fig.tight_layout()
    fig.savefig(save_dir / "spectral_intensity_maps.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    if baseline_losses:
        axes[0].plot(baseline_losses, label="Candidate (self-reported)")
    if ref_losses:
        axes[0].plot(ref_losses, label="Reference")
    axes[0].set_yscale("log")
    axes[0].set_title("Training Loss")
    axes[0].set_xlabel("Iteration")
    axes[0].legend()

    idx = list(range(len(spec["wavelengths"])))
    axes[1].bar([i - 0.25 for i in idx], baseline_eval["target_spectral_ratios"], width=0.25, label="Target")
    axes[1].bar(idx, baseline_eval["pred_spectral_ratios"], width=0.25, label="Candidate")
    axes[1].bar([i + 0.25 for i in idx], reference_eval["pred_spectral_ratios"], width=0.25, label="Reference")
    axes[1].set_xticks(idx)
    axes[1].set_xticklabels([f"{wl*1e9:.0f}nm" for wl in spec["wavelengths"]])
    axes[1].set_title("Spectral Power Ratios")
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(save_dir / "loss_and_spectral_ratios.png", dpi=180)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    shared.add_common_cli_args(
        parser,
        default_artifacts_dir=THIS_DIR / "artifacts",
        default_reference_steps=40,
    )
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = Path(args.candidate) if args.candidate else TASK_DIR / "baseline" / "init.py"

    spec = problem_spec.make_spec(
        baseline_steps=args.baseline_steps, reference_steps=args.reference_steps
    )
    device = args.device or "cpu"
    shared.configure_torchoptics(spec["spacing"], spec["reference_wavelength"])

    thickness_spec = shared.ArraySpec(
        shape=tuple(spec["thickness_shape"]),
        max_abs=float(spec["max_thickness_m"]),
        min_value=0.0,
        max_value=float(spec["max_thickness_m"]),
    )

    # ---- candidate: isolated subprocess, arrays only ----
    t0 = time.time()
    try:
        submitted = shared.run_candidate_arrays(
            candidate_path,
            problem=problem_spec.candidate_problem(spec),
            arrays={"thickness": thickness_spec},
            optional_arrays=("loss_history",),
            timeout_s=args.candidate_timeout,
        )
    except shared.CandidateRejected as exc:
        shared.write_rejection(artifacts_dir, TASK_NAME, candidate_path, str(exc))
        print(f"Candidate rejected: {exc}", file=sys.stderr)
        return 3
    t1 = time.time()

    # ---- reference: trusted, in-process, held to an arrays-only contract too ----
    ref_res = reference_solver.solve(spec=spec, device=device, seed=args.seed)
    t2 = time.time()
    ref_phase_spec = shared.ArraySpec(
        shape=(int(spec["n_wavelengths"]), int(spec["shape"]), int(spec["shape"])),
        max_abs=1.0e4,
    )
    try:
        ref_phases = shared.validate_array(
            ref_res["phase_per_wavelength"], "reference phase_per_wavelength", ref_phase_spec
        )
    except shared.CandidateRejected as exc:
        raise RuntimeError(f"reference solver produced an invalid submission: {exc}") from exc

    # ---- scoring: one metric function, both design spaces owned here ----
    fields = _input_fields(spec, device)
    baseline_eval = _score_outputs(
        _outputs_shared_stack(submitted["thickness"], spec, device, fields), spec, device
    )
    reference_eval = _score_outputs(
        _outputs_per_wavelength(ref_phases, spec, device, fields), spec, device
    )

    baseline_valid = (
        baseline_eval["mean_target_efficiency"] >= spec["valid_mean_target_efficiency_min"]
        and baseline_eval["mean_crosstalk"] <= spec["valid_mean_crosstalk_max"]
        and baseline_eval["mean_score"] >= spec["valid_mean_score_min"]
    )
    reference_better = (
        reference_eval["mean_score"] >= baseline_eval["mean_score"] + float(spec["better_score_margin"])
        and reference_eval["mean_shape_cosine"]
        >= baseline_eval["mean_shape_cosine"] + float(spec["better_shape_margin"])
    )

    candidate_losses = [float(v) for v in np.asarray(submitted.get("loss_history", [])).ravel()]
    _plot_outputs(
        spec,
        baseline_eval,
        reference_eval,
        candidate_losses,
        list(ref_res.get("loss_history") or []),
        device,
        artifacts_dir,
    )

    def _strip(ev: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in ev.items() if k != "per_wavelength"}
        out["per_wavelength"] = [
            {k: v for k, v in x.items() if k != "intensity"} for x in ev["per_wavelength"]
        ]
        return out

    summary = {
        "task": TASK_NAME,
        "candidate_module": str(candidate_path.resolve()),
        "candidate_execution": "isolated_subprocess",
        "spec": {k: v for k, v in spec.items() if k != "thickness_shape"},
        "timing_seconds": {
            "baseline": round(t1 - t0, 3),
            "reference": round(t2 - t1, 3),
        },
        "baseline": {
            "valid": baseline_valid,
            "design_space": "shared_dispersive_thickness_stack",
            **_strip(baseline_eval),
        },
        "reference": {
            "oracle_backend": ref_res.get("oracle_backend", "unknown"),
            "design_space": "per_wavelength_phase_mask (deliberate upper bound)",
            "better_than_baseline": reference_better,
            **_strip(reference_eval),
        },
    }

    with open(artifacts_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
