"""Task A4 (fault-tolerant WFS fusion): score a candidate that runs in its own process.

The candidate is launched as a standalone script and gets the multi-sensor slope
stream (shape ``(n_cases, n_wfs, 2*n_subap)`` -- observations only, never the
ground-truth phase or which sensors were corrupted). It returns a
``(n_cases, n_act)`` command matrix; this process recomputes every metric from
that matrix. The IsolationForest anomaly detector is part of the *reference*
oracle only -- the candidate never sees it, matching the original contract
where the candidate's ``control_model`` did not include an anomaly model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest

VERIFICATION_DIR = Path(__file__).resolve().parent
TASK_DIR = VERIFICATION_DIR.parent
if str(VERIFICATION_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFICATION_DIR))


def _find_repo_root() -> Path:
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    raise RuntimeError("could not locate repo root for adaptive_fault_tolerant_fusion")


_REPO = _find_repo_root()
if str(_REPO / "benchmarks" / "_shared") not in sys.path:
    sys.path.insert(0, str(_REPO / "benchmarks" / "_shared"))

# Invariant 1: every scoring dependency is resident before the candidate runs.
import optics_adaptive as shared  # noqa: E402

from reference_controller import fuse_and_compute_dm_commands as reference_controller  # noqa: E402

TASK_NAME = "task4_fault_tolerant_fusion"

P95_WEIGHT = 0.4
STREHL_WEIGHT = 1.0

SCORE_ANCHORS = {
    "mean_rms_good": 0.95,
    "mean_rms_bad": 1.75,
    "p95_rms_good": 1.20,
    "p95_rms_bad": 2.05,
    "strehl_good": 0.35,
    "strehl_bad": 0.18,
}
SCORE_WEIGHTS = {
    "mean_rms": 0.45,
    "p95_rms": 0.35,
    "strehl": 0.20,
}


def make_system(seed: int = 53):
    rng = np.random.default_rng(seed)
    # No plant_gain draw here (plant_gain_sigma=None), matching the original
    # make_system for this task, which never modeled DM gain mismatch.
    sys_cfg = shared.build_optics_system(rng, plant_gain_sigma=None)

    zern = sys_cfg["zern"]
    slopes_from_phase = sys_cfg["slopes_from_phase"]
    n_slopes = sys_cfg["reconstructor"].shape[1]

    # Train anomaly detector on clean single-sensor slope vectors.
    n_train = 900
    train_samples = np.zeros((n_train, n_slopes), dtype=np.float64)
    for i in range(n_train):
        coeff = rng.normal(0.0, 0.35, size=zern.shape[0])
        phase = np.tensordot(coeff, zern, axes=(0, 0))
        clean_slopes = slopes_from_phase(phase) + rng.normal(0.0, 0.01, size=n_slopes)
        train_samples[i] = clean_slopes

    anomaly_model = IsolationForest(
        n_estimators=260,
        contamination=0.08,
        random_state=seed + 123,
    )
    anomaly_model.fit(train_samples)

    sys_cfg["control_model"] = {
        "anomaly_model": anomaly_model,
        "inlier_fraction": 0.4,
        "score_temperature": 0.08,
    }
    return sys_cfg


def make_multi_wfs_observation(rng, true_slopes):
    # 5 WFS sensors: nominal channels with random severe faults.
    n_wfs = 5
    slopes_multi = np.stack(
        [true_slopes + rng.normal(0.0, 0.01, size=true_slopes.shape) for _ in range(n_wfs)], axis=0
    )

    n_bad = 3
    bad_ids = rng.choice(n_wfs, size=n_bad, replace=False)
    for bad_id in bad_ids:
        gain = float(rng.uniform(3.0, 5.2))
        if rng.random() < 0.2:
            gain *= -1.0

        slopes_multi[bad_id] = gain * slopes_multi[bad_id] + rng.normal(0.0, 1.0, size=true_slopes.shape)

        spike_idx = rng.choice(true_slopes.size, size=true_slopes.size // 2, replace=False)
        slopes_multi[bad_id, spike_idx] += rng.normal(0.0, 3.0, size=spike_idx.size)

        dropout_idx = rng.choice(true_slopes.size, size=true_slopes.size // 6, replace=False)
        slopes_multi[bad_id, dropout_idx] = 0.0

    return slopes_multi


def make_scenario(sys_cfg, n_cases: int) -> dict:
    """Draw the whole disturbance + fault stream up front (rng order unchanged)."""
    rng = sys_cfg["rng"]
    zern = sys_cfg["zern"]
    n_pix = sys_cfg["n_pix"]
    n_slopes = sys_cfg["reconstructor"].shape[1]
    slopes_from_phase = sys_cfg["slopes_from_phase"]

    phases = np.zeros((n_cases, n_pix, n_pix), dtype=np.float64)
    slopes_multi_stream = np.zeros((n_cases, 5, n_slopes), dtype=np.float64)

    for i in range(n_cases):
        coeff = rng.normal(0.0, 0.35, size=zern.shape[0])
        phase = np.tensordot(coeff, zern, axes=(0, 0))

        true_slopes = slopes_from_phase(phase)
        slopes_multi = make_multi_wfs_observation(rng, true_slopes)

        phases[i] = phase
        slopes_multi_stream[i] = slopes_multi

    return {"phases": phases, "slopes_multi": slopes_multi_stream}


def score_commands(sys_cfg, scenario, get_command, max_voltage: float) -> dict:
    pupil = sys_cfg["pupil"]
    valid_mask = sys_cfg["valid_mask"]
    dm_surface = sys_cfg["dm_surface"]
    strehl_ref = sys_cfg["strehl_ref"]
    n_act = sys_cfg["n_act"]

    phases = scenario["phases"]
    slopes_multi_stream = scenario["slopes_multi"]
    n_cases = len(phases)

    rms_list = []
    strehl_list = []
    example = None

    for i in range(n_cases):
        cmd = np.asarray(get_command(i, slopes_multi_stream[i]), dtype=np.float64)

        if cmd.shape != (n_act,):
            raise ValueError(f"Invalid output shape: {cmd.shape}, expected {(n_act,)}")
        if not np.all(np.isfinite(cmd)):
            raise ValueError("Controller output contains NaN/Inf")
        if np.any(np.abs(cmd) > max_voltage + 1e-8):
            raise ValueError("Controller output violates voltage bounds")

        residual = (phases[i] - dm_surface(cmd)) * pupil
        rms = float(np.sqrt(np.mean(residual[valid_mask] ** 2)))
        strehl, i_psf = shared.strehl_from_residual(residual, pupil, strehl_ref)

        rms_list.append(rms)
        strehl_list.append(strehl)

        if i == 0:
            example = {
                "phase": phases[i],
                "residual": residual,
                "psf": i_psf / (i_psf.sum() + 1e-12),
            }

    mean_rms = float(np.mean(rms_list))
    p95_rms = float(np.quantile(rms_list, 0.95))
    worst_rms = float(np.max(rms_list))
    mean_strehl = float(np.mean(strehl_list))
    raw_cost = float(mean_rms + P95_WEIGHT * p95_rms - STREHL_WEIGHT * mean_strehl)

    utilities = {
        "mean_rms": shared.utility_lower_better(
            mean_rms, SCORE_ANCHORS["mean_rms_good"], SCORE_ANCHORS["mean_rms_bad"]
        ),
        "p95_rms": shared.utility_lower_better(
            p95_rms, SCORE_ANCHORS["p95_rms_good"], SCORE_ANCHORS["p95_rms_bad"]
        ),
        "strehl": shared.utility_higher_better(
            mean_strehl, SCORE_ANCHORS["strehl_good"], SCORE_ANCHORS["strehl_bad"]
        ),
    }
    score_01 = shared.weighted_score(utilities, SCORE_WEIGHTS)

    return {
        "mean_rms": mean_rms,
        "p95_rms": p95_rms,
        "worst_rms": worst_rms,
        "mean_strehl": mean_strehl,
        "raw_cost_lower_is_better": raw_cost,
        "score_0_to_1_higher_is_better": score_01,
        "score_percent": 100.0 * score_01,
        "example": example,
    }


def build_problem(sys_cfg, scenario, max_voltage: float) -> dict:
    """Exactly what the candidate subprocess is allowed to see.

    No anomaly model: the baseline candidate never had one either (the
    reference's IsolationForest was oracle-only). ``uses_prev_commands`` is 0
    since the original loop always called with ``prev_commands=None``.
    """
    problem = {
        "slopes_multi": scenario["slopes_multi"],
        "reconstructor": sys_cfg["reconstructor"],
        "max_voltage": np.float64(max_voltage),
        "n_act": np.int64(sys_cfg["n_act"]),
        "uses_prev_commands": np.int64(0),
    }
    return problem


def main() -> int:
    parser = argparse.ArgumentParser()
    shared.add_common_cli_args(
        parser,
        default_candidate=TASK_DIR / "baseline" / "init.py",
        default_max_voltage=0.50,
    )
    parser.add_argument("--cases", type=int, default=320)
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else VERIFICATION_DIR / "outputs"
    candidate_path = Path(args.candidate)

    sys_cfg = make_system(seed=53)
    scenario = make_scenario(sys_cfg, args.cases)

    try:
        commands = shared.run_candidate_controller(
            candidate_path,
            problem=build_problem(sys_cfg, scenario, args.max_voltage),
            n_steps=args.cases,
            n_act=sys_cfg["n_act"],
            max_voltage=args.max_voltage,
            timeout_s=args.candidate_timeout,
        )
    except shared.CandidateRejected as exc:
        shared.write_rejection(out_dir, TASK_NAME, candidate_path, str(exc))
        print(f"Candidate rejected: {exc}", file=sys.stderr)
        return 3

    baseline_metrics = score_commands(
        sys_cfg, scenario, lambda i, sm: commands[i], args.max_voltage
    )

    sys_cfg_ref = make_system(seed=53)
    scenario_ref = make_scenario(sys_cfg_ref, args.cases)
    reference_metrics = score_commands(
        sys_cfg_ref,
        scenario_ref,
        lambda i, sm: reference_controller(
            sm,
            sys_cfg_ref["reconstructor"],
            sys_cfg_ref["control_model"],
            None,
            max_voltage=args.max_voltage,
        ),
        args.max_voltage,
    )

    payload = {
        "task": TASK_NAME,
        "benchmark_profile": "v3_fault_stress",
        "candidate_module": str(candidate_path.resolve()),
        "candidate_execution": "isolated_subprocess",
        "oracle_backend": "IsolationForest weighted inlier fusion",
        "fault_scenario": "5 WFS channels with 3 severe random corruptions per case",
        "p95_weight": P95_WEIGHT,
        "strehl_weight": STREHL_WEIGHT,
        "score_mode": "0_to_1_higher_is_better",
        "score_anchors": SCORE_ANCHORS,
        "score_weights": SCORE_WEIGHTS,
        "baseline": {k: v for k, v in baseline_metrics.items() if k != "example"},
        "reference": {k: v for k, v in reference_metrics.items() if k != "example"},
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    shared.save_comparison_plots(
        out_dir,
        baseline_metrics,
        reference_metrics,
        ["score_0_to_1_higher_is_better", "mean_rms", "p95_rms", "mean_strehl"],
    )
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(json.dumps(payload, indent=2))
    print(f"Saved figures/metrics to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
