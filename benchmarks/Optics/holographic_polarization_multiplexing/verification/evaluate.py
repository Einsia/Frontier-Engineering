"""Verification script for Holographic H4: polarization multiplexing.

Contract (changed -- see ``benchmarks/_shared/optics_holographic.py``):

* the problem definition lives in ``verification/problem_spec.py``, not in the
  candidate;
* the candidate runs as its own process and returns only the decision variables
  -- the Jones ``phase_x`` / ``phase_y`` map of each layer -- in ``submission.npz``;
* this file builds both polarised inputs, runs the propagation, builds both
  target maps, and computes every metric.

The old evaluator ran *no physics at all*: it read ``output_field_x``,
``output_field_y``, ``target_map_x`` and ``target_map_y`` from the candidate's
return value and compared them against each other. A submission could therefore
hand back any pair it liked, including two identical arrays. Only float arrays
cross the boundary now, and both sides of every comparison are built here.
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
    raise RuntimeError("could not locate repo root for holographic_polarization_multiplexing")


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
def _evaluate_phases(
    phase_x: np.ndarray,
    phase_y: np.ndarray,
    spec: dict[str, Any],
    device: str,
    fields,
    targets,
) -> dict[str, Any]:
    field_x, field_y = fields
    target_x, target_y = targets

    px = [torch.as_tensor(p, dtype=torch.double, device=device) for p in phase_x]
    py = [torch.as_tensor(p, dtype=torch.double, device=device) for p in phase_y]

    with torch.no_grad():
        out_x = shared.polarization_forward(field_x, spec["layer_z"], spec["output_z"], px, py)
        out_y = shared.polarization_forward(field_y, spec["layer_z"], spec["output_z"], px, py)

        map_x = out_x.intensity().sum(dim=-3)
        map_y = out_y.intensity().sum(dim=-3)

        map_x_norm = map_x / (map_x.sum() + 1e-12)
        map_y_norm = map_y / (map_y.sum() + 1e-12)

        match_x = shared.cosine_similarity(map_x_norm.detach().cpu(), target_x.detach().cpu())
        match_y = shared.cosine_similarity(map_y_norm.detach().cpu(), target_y.detach().cpu())
        mean_match = 0.5 * (match_x + match_y)

        xg, yg = out_x.meshgrid()
        radius = float(spec["roi_radius_m"])
        masks_pattern_x = shared.masks_for_centers(xg, yg, spec["pattern_x_centers"], radius, map_x.dtype)
        masks_pattern_y = shared.masks_for_centers(xg, yg, spec["pattern_y_centers"], radius, map_x.dtype)

        def _sum_on(m, masks):
            return torch.stack([(m * mask).sum() for mask in masks]).sum()

        def _powers_on(m, masks):
            return torch.stack([(m * mask).sum() for mask in masks])

        p_x_on_x = _sum_on(map_x, masks_pattern_x)
        p_x_on_y = _sum_on(map_x, masks_pattern_y)
        p_y_on_x = _sum_on(map_y, masks_pattern_x)
        p_y_on_y = _sum_on(map_y, masks_pattern_y)
        p_x_focus = _powers_on(map_x, masks_pattern_x)
        p_y_focus = _powers_on(map_y, masks_pattern_y)

        sep_x = float((p_x_on_x / (p_x_on_x + p_x_on_y + 1e-12)).item())
        sep_y = float((p_y_on_y / (p_y_on_x + p_y_on_y + 1e-12)).item())
        separation = 0.5 * (sep_x + sep_y)
        own_eff_x = float((p_x_on_x / (map_x.sum() + 1e-12)).item())
        own_eff_y = float((p_y_on_y / (map_y.sum() + 1e-12)).item())
        own_efficiency = 0.5 * (own_eff_x + own_eff_y)

        ratio_x = p_x_focus / (p_x_focus.sum() + 1e-12)
        ratio_y = p_y_focus / (p_y_focus.sum() + 1e-12)
        target_ratio_x = torch.tensor(spec["pattern_x_ratios"], dtype=torch.double, device=ratio_x.device)
        target_ratio_x = target_ratio_x / target_ratio_x.sum()
        target_ratio_y = torch.tensor(spec["pattern_y_ratios"], dtype=torch.double, device=ratio_y.device)
        target_ratio_y = target_ratio_y / target_ratio_y.sum()

        ratio_mae_x = float(torch.mean(torch.abs(ratio_x - target_ratio_x)).item())
        ratio_mae_y = float(torch.mean(torch.abs(ratio_y - target_ratio_y)).item())

    mean_ratio_mae = 0.5 * (ratio_mae_x + ratio_mae_y)
    ratio_score = math.exp(-mean_ratio_mae / float(spec["score_ratio_scale"]))
    efficiency_score = shared.clip01(own_efficiency / float(spec["score_eff_target"]))
    score = (
        (max(separation, 0.0) ** 0.55)
        * (max(ratio_score, 0.0) ** 0.20)
        * (efficiency_score**0.25)
        * (max(mean_match, 0.0) ** 0.05)
    )

    return {
        "match_x": match_x,
        "match_y": match_y,
        "mean_match": mean_match,
        "separation_x": sep_x,
        "separation_y": sep_y,
        "separation": separation,
        "own_efficiency": own_efficiency,
        "efficiency_score": efficiency_score,
        "ratio_mae_x": ratio_mae_x,
        "ratio_mae_y": ratio_mae_y,
        "mean_ratio_mae": mean_ratio_mae,
        "ratio_score": ratio_score,
        "pred_ratio_x": ratio_x.detach().cpu().tolist(),
        "pred_ratio_y": ratio_y.detach().cpu().tolist(),
        "target_ratio_x": target_ratio_x.detach().cpu().tolist(),
        "target_ratio_y": target_ratio_y.detach().cpu().tolist(),
        "score": shared.clip01(score),
        "output_map_x": map_x.detach().cpu(),
        "output_map_y": map_y.detach().cpu(),
    }


# --------------------------------------------------------------------------- #
# Reporting.
# --------------------------------------------------------------------------- #
def _plot_outputs(base_eval, ref_eval, targets, baseline_losses, ref_losses, save_dir: Path):
    plt = shared.use_agg_matplotlib()
    _norm = shared.norm_for_plot
    target_x, target_y = (t.detach().cpu() for t in targets)

    fig, axes = plt.subplots(2, 3, figsize=(11, 6.5))
    axes[0][0].imshow(_norm(target_x), cmap="magma")
    axes[0][0].set_title("Target (X-pol input)")
    axes[0][1].imshow(_norm(base_eval["output_map_x"]), cmap="magma")
    axes[0][1].set_title("Candidate Output")
    axes[0][2].imshow(_norm(ref_eval["output_map_x"]), cmap="magma")
    axes[0][2].set_title("Reference Output")

    axes[1][0].imshow(_norm(target_y), cmap="magma")
    axes[1][0].set_title("Target (Y-pol input)")
    axes[1][1].imshow(_norm(base_eval["output_map_y"]), cmap="magma")
    axes[1][1].set_title("Candidate Output")
    axes[1][2].imshow(_norm(ref_eval["output_map_y"]), cmap="magma")
    axes[1][2].set_title("Reference Output")

    for i in range(2):
        for j in range(3):
            axes[i][j].axis("off")

    fig.tight_layout()
    fig.savefig(save_dir / "polarization_maps.png", dpi=180)
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

    labels = ["Match", "Separation", "RatioScore", "Score"]
    base_vals = [base_eval["mean_match"], base_eval["separation"], base_eval["ratio_score"], base_eval["score"]]
    ref_vals = [ref_eval["mean_match"], ref_eval["separation"], ref_eval["ratio_score"], ref_eval["score"]]
    x = list(range(len(labels)))

    axes[1].bar([i - 0.2 for i in x], base_vals, width=0.4, label="Candidate")
    axes[1].bar([i + 0.2 for i in x], ref_vals, width=0.4, label="Reference")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels)
    axes[1].set_ylim(0.0, 1.05)
    axes[1].set_title("Key Metrics")
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(save_dir / "loss_and_metrics.png", dpi=180)
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
            arrays={"phase_x": phase_spec, "phase_y": phase_spec},
            optional_arrays=("loss_history",),
            timeout_s=args.candidate_timeout,
        )
    except shared.CandidateRejected as exc:
        shared.write_rejection(artifacts_dir, TASK_NAME, candidate_path, str(exc))
        print(f"Candidate rejected: {exc}", file=sys.stderr)
        return 3
    t1 = time.time()

    # ---- reference: trusted, in-process, held to the same contract ----
    ref_res = reference_solver.solve(spec=spec, device=device, seed=args.seed)
    t2 = time.time()
    try:
        ref_px = shared.validate_array(ref_res["phase_x"], "reference phase_x", phase_spec)
        ref_py = shared.validate_array(ref_res["phase_y"], "reference phase_y", phase_spec)
    except shared.CandidateRejected as exc:
        raise RuntimeError(f"reference solver produced an invalid submission: {exc}") from exc

    # ---- scoring: inputs, propagation and targets all built here ----
    fields = shared.polarized_gaussian_inputs(
        spec["shape"], spec["waist_radius"], spec["wavelength"], device
    )
    targets = (
        shared.ratio_weighted_map(
            spec["shape"], spec["waist_radius"], spec["pattern_x_centers"], spec["pattern_x_ratios"], device
        ),
        shared.ratio_weighted_map(
            spec["shape"], spec["waist_radius"], spec["pattern_y_centers"], spec["pattern_y_ratios"], device
        ),
    )

    baseline_eval = _evaluate_phases(
        submitted["phase_x"], submitted["phase_y"], spec, device, fields, targets
    )
    reference_eval = _evaluate_phases(ref_px, ref_py, spec, device, fields, targets)

    baseline_valid = (
        baseline_eval["mean_match"] >= spec["valid_match_min"]
        and baseline_eval["separation"] >= spec["valid_separation_min"]
        and baseline_eval["score"] >= spec["valid_score_min"]
    )
    reference_better = (
        reference_eval["score"] >= baseline_eval["score"] + float(spec["better_score_margin"])
        and reference_eval["separation"] >= baseline_eval["separation"] + float(spec["better_sep_margin"])
    )

    candidate_losses = [float(v) for v in np.asarray(submitted.get("loss_history", [])).ravel()]
    _plot_outputs(
        baseline_eval,
        reference_eval,
        targets,
        candidate_losses,
        list(ref_res.get("loss_history") or []),
        artifacts_dir,
    )

    def _strip(ev: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in ev.items() if not k.startswith("output_")}

    summary = {
        "task": TASK_NAME,
        "candidate_module": str(candidate_path.resolve()),
        "candidate_execution": "isolated_subprocess",
        "spec": {k: v for k, v in spec.items() if k != "phase_shape"},
        "timing_seconds": {
            "baseline": round(t1 - t0, 3),
            "reference": round(t2 - t1, 3),
        },
        "baseline": {"valid": baseline_valid, **_strip(baseline_eval)},
        "reference": {
            "oracle_backend": ref_res.get("oracle_backend", "unknown"),
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
