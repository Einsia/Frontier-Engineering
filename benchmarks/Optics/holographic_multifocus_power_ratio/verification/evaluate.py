"""Verification script for Holographic H1: multifocus power-ratio control.

Contract (changed -- see ``benchmarks/_shared/optics_holographic.py``):

* the problem definition lives in ``verification/problem_spec.py``, not in the
  candidate;
* the candidate runs as its own process and returns only the decision variables
  -- the phase map of each modulator layer -- as arrays in ``submission.npz``;
* this file builds the optical system from those arrays, propagates the field,
  builds the target, and computes every metric itself.

No callable, field, system or self-reported number crosses the boundary, which
is what makes the archived ``_LookupSystem`` attack (a fake ``measure_at_z``
returning the candidate's own target) unexpressible rather than merely detected.
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
    raise RuntimeError("could not locate repo root for holographic_multifocus_power_ratio")


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
# Scorer-owned forward model + metrics.
# --------------------------------------------------------------------------- #
def _simulate(phases: np.ndarray, spec: dict[str, Any], device: str):
    """Build the system from raw phase maps and propagate to the output plane."""
    system = shared.build_phase_system(phases, spec["layer_z"], device)
    input_field = shared.gaussian_input_field(
        spec["shape"], spec["waist_radius"], device=device
    )
    with torch.no_grad():
        return system.measure_at_z(input_field, z=float(spec["output_z"]))


def _compute_metrics(output_field, target_field, spec: dict[str, Any]) -> dict[str, Any]:
    x, y = output_field.meshgrid()
    intensity = output_field.intensity()
    pred_norm = intensity / (intensity.sum() + 1e-12)

    target_intensity = target_field.intensity().to(intensity.device)
    target_norm = target_intensity / (target_intensity.sum() + 1e-12)

    roi_radius = float(spec["roi_radius_m"])
    roi_powers = []
    for cx, cy in spec["focus_centers"]:
        mask = ((x - cx) ** 2 + (y - cy) ** 2) <= roi_radius**2
        roi_powers.append((intensity * mask.to(intensity.dtype)).sum())

    roi_powers_t = torch.stack(roi_powers)
    focus_power = roi_powers_t.sum()
    total_power = intensity.sum() + 1e-12

    target_ratios = torch.tensor(spec["focus_ratios"], dtype=torch.double, device=intensity.device)
    target_ratios = target_ratios / target_ratios.sum()
    pred_ratios = roi_powers_t / (focus_power + 1e-12)

    ratio_mae = torch.mean(torch.abs(pred_ratios - target_ratios)).item()
    efficiency = (focus_power / total_power).item()
    leakage = 1.0 - efficiency
    ratio_score = math.exp(-ratio_mae / float(spec["score_ratio_scale"]))
    efficiency_score = shared.clip01(efficiency / float(spec["score_eff_target"]))
    shape_cosine = shared.cosine_similarity(pred_norm, target_norm)
    shape_l1 = float(torch.mean(torch.abs(pred_norm - target_norm)).item())
    score = (efficiency_score**0.58) * (max(ratio_score, 0.0) ** 0.22) * (max(shape_cosine, 0.0) ** 0.20)

    return {
        "ratio_mae": ratio_mae,
        "efficiency": efficiency,
        "leakage": leakage,
        "ratio_score": ratio_score,
        "efficiency_score": efficiency_score,
        "shape_cosine": shape_cosine,
        "shape_l1": shape_l1,
        "score": shared.clip01(score),
        "pred_ratios": pred_ratios.detach().cpu().tolist(),
        "target_ratios": target_ratios.detach().cpu().tolist(),
        "intensity": intensity.detach().cpu(),
    }


def _evaluate_phases(phases: np.ndarray, spec: dict[str, Any], device: str, target_field):
    return _compute_metrics(_simulate(phases, spec, device), target_field, spec)


# --------------------------------------------------------------------------- #
# Reporting.
# --------------------------------------------------------------------------- #
def _plot_outputs(spec, target_field, baseline_metrics, ref_metrics, baseline_losses, ref_losses, save_dir: Path):
    plt = shared.use_agg_matplotlib()
    _norm = shared.norm_for_plot

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    axes[0].imshow(_norm(target_field.intensity().detach().cpu()), cmap="magma")
    axes[0].set_title("Target Intensity")
    axes[1].imshow(_norm(baseline_metrics["intensity"]), cmap="magma")
    axes[1].set_title("Candidate Output")
    axes[2].imshow(_norm(ref_metrics["intensity"]), cmap="magma")
    axes[2].set_title("Reference Output")
    for ax in axes:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(save_dir / "intensity_maps.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    idx = list(range(len(spec["focus_ratios"])))
    axes[0].bar([i - 0.25 for i in idx], baseline_metrics["target_ratios"], width=0.25, label="Target")
    axes[0].bar(idx, baseline_metrics["pred_ratios"], width=0.25, label="Candidate")
    axes[0].bar([i + 0.25 for i in idx], ref_metrics["pred_ratios"], width=0.25, label="Reference")
    axes[0].set_title("Focus Power Ratios")
    axes[0].set_xlabel("Focus Index")
    axes[0].legend()

    if baseline_losses:
        axes[1].plot(baseline_losses, label="Candidate (self-reported)")
    axes[1].plot(ref_losses, label="Reference")
    axes[1].set_yscale("log")
    axes[1].set_title("Training Loss")
    axes[1].set_xlabel("Iteration")
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(save_dir / "ratios_and_losses.png", dpi=180)
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
    shared.configure_torchoptics(spec["spacing"], spec["wavelength"])

    phase_spec = shared.ArraySpec(
        shape=tuple(spec["phase_shape"]), max_abs=float(spec["max_abs_phase"])
    )

    # ---- candidate: isolated subprocess, arrays only ----
    t0 = time.time()
    try:
        submitted = shared.run_candidate_arrays(
            candidate_path,
            problem=problem_spec.candidate_problem(spec),
            arrays={"phases": phase_spec},
            optional_arrays=("loss_history",),
            timeout_s=args.candidate_timeout,
        )
    except shared.CandidateRejected as exc:
        shared.write_rejection(artifacts_dir, TASK_NAME, candidate_path, str(exc))
        print(f"Candidate rejected: {exc}", file=sys.stderr)
        return 3
    t1 = time.time()

    # ---- reference: trusted, in-process, but held to the same contract ----
    ref_res = reference_solver.solve(spec=spec, device=device, seed=args.seed)
    t2 = time.time()
    try:
        ref_phases = shared.validate_array(ref_res["phases"], "reference phases", phase_spec)
    except shared.CandidateRejected as exc:
        raise RuntimeError(f"reference solver produced an invalid submission: {exc}") from exc

    # ---- scoring: one target, one forward model, both owned here ----
    target_field = shared.build_target_field(
        spec["shape"],
        spec["waist_radius"],
        spec["focus_centers"],
        spec["focus_ratios"],
        spec["output_z"],
        device,
    )
    baseline_metrics = _evaluate_phases(submitted["phases"], spec, device, target_field)
    ref_metrics = _evaluate_phases(ref_phases, spec, device, target_field)

    baseline_valid = (
        baseline_metrics["ratio_mae"] <= spec["valid_ratio_mae_max"]
        and baseline_metrics["efficiency"] >= spec["valid_efficiency_min"]
        and baseline_metrics["score"] >= spec["valid_score_min"]
    )
    reference_better = (
        ref_metrics["score"] >= baseline_metrics["score"] + float(spec["better_score_margin"])
        and ref_metrics["shape_cosine"] >= baseline_metrics["shape_cosine"] + float(spec["better_shape_margin"])
    )

    candidate_losses = [float(v) for v in np.asarray(submitted.get("loss_history", [])).ravel()]
    _plot_outputs(
        spec,
        target_field,
        baseline_metrics,
        ref_metrics,
        candidate_losses,
        list(ref_res.get("loss_history") or []),
        artifacts_dir,
    )

    summary = {
        "task": TASK_NAME,
        "candidate_module": str(candidate_path.resolve()),
        "candidate_execution": "isolated_subprocess",
        "spec": {k: v for k, v in spec.items() if k != "phase_shape"},
        "timing_seconds": {
            "baseline": round(t1 - t0, 3),
            "reference": round(t2 - t1, 3),
        },
        "baseline": {
            "metrics": {k: v for k, v in baseline_metrics.items() if k != "intensity"},
            "valid": baseline_valid,
        },
        "reference": {
            "oracle_backend": ref_res.get("oracle_backend", "unknown"),
            "metrics": {k: v for k, v in ref_metrics.items() if k != "intensity"},
            "better_than_baseline": reference_better,
        },
    }

    with open(artifacts_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
