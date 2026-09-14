"""Task A3 (energy-aware DM control): score a candidate that runs in its own process.

The candidate is launched as a standalone script and gets the WFS slope stream
(observations only, never the ground-truth phase). It returns a
``(n_cases, n_act)`` command matrix; this process replays the actuator lag
recurrence and recomputes every metric -- RMS, sparsity, command energy, Strehl
-- from that matrix, never from anything the candidate reports about itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

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
    raise RuntimeError("could not locate repo root for adaptive_energy_aware_control")


_REPO = _find_repo_root()
if str(_REPO / "benchmarks" / "_shared") not in sys.path:
    sys.path.insert(0, str(_REPO / "benchmarks" / "_shared"))

# Invariant 1: every scoring dependency is resident before the candidate runs.
import optics_adaptive as shared  # noqa: E402

from reference_controller import compute_dm_commands as reference_controller  # noqa: E402

TASK_NAME = "task3_energy_aware_control"

ENERGY_WEIGHT = 2.2
ACTUATOR_LAG = 0.74
SLOPE_DELAY_NOISE = 0.004
PHASE_AR = 0.80

SCORE_ANCHORS = {
    "mean_rms_good": 1.55,
    "mean_rms_bad": 2.25,
    "mean_abs_good": 0.08,
    "mean_abs_bad": 0.36,
    "sparsity_good": 0.40,
    "sparsity_bad": 0.00,
    "strehl_good": 0.22,
    "strehl_bad": 0.08,
}
SCORE_WEIGHTS = {
    "mean_rms": 0.15,
    "mean_abs": 0.60,
    "sparsity": 0.15,
    "strehl": 0.10,
}


def make_system(seed: int = 41):
    rng = np.random.default_rng(seed)
    sys_cfg = shared.build_optics_system(
        rng,
        plant_gain_sigma=0.16,
        plant_gain_clip=(0.66, 1.34),
    )

    sys_cfg["control_model"] = {
        "h_matrix": sys_cfg["h_matrix"],
        "lasso_alpha": 2e-4,
        "lasso_max_iter": 2500,
        "lasso_tol": 1e-5,
        "delay_comp_gain": 0.35,
        "temporal_blend": 0.24,
    }
    return sys_cfg


def make_scenario(sys_cfg, n_cases: int) -> dict:
    """Draw the whole disturbance stream up front (rng order unchanged)."""
    rng = sys_cfg["rng"]
    zern = sys_cfg["zern"]
    n_slopes = sys_cfg["reconstructor"].shape[1]
    slopes_from_phase = sys_cfg["slopes_from_phase"]

    phases = np.zeros((n_cases, sys_cfg["n_pix"], sys_cfg["n_pix"]), dtype=np.float64)
    slopes_stream = np.zeros((n_cases, n_slopes), dtype=np.float64)

    coeff_state = rng.normal(0.0, 0.45, size=zern.shape[0])
    delayed_slopes = np.zeros(n_slopes, dtype=np.float64)

    for i in range(n_cases):
        coeff_state = PHASE_AR * coeff_state + rng.normal(0.0, 0.28, size=zern.shape[0])
        phase = np.tensordot(coeff_state, zern, axes=(0, 0))

        true_slopes = slopes_from_phase(phase)
        slopes = delayed_slopes + rng.normal(0.0, SLOPE_DELAY_NOISE, size=true_slopes.shape)
        delayed_slopes = true_slopes

        phases[i] = phase
        slopes_stream[i] = slopes

    return {"phases": phases, "slopes": slopes_stream}


def score_commands(sys_cfg, scenario, get_command, max_voltage: float) -> dict:
    pupil = sys_cfg["pupil"]
    valid_mask = sys_cfg["valid_mask"]
    dm_surface_true = sys_cfg["dm_surface_true"]
    strehl_ref = sys_cfg["strehl_ref"]
    n_act = sys_cfg["n_act"]

    phases = scenario["phases"]
    slopes_stream = scenario["slopes"]
    n_cases = len(slopes_stream)

    rms_list = []
    strehl_list = []
    mean_abs_u = []
    sparsity = []
    example = None

    prev_applied = np.zeros(n_act, dtype=np.float64)

    for i in range(n_cases):
        cmd = np.asarray(get_command(i, slopes_stream[i], prev_applied), dtype=np.float64)

        if cmd.shape != (n_act,):
            raise ValueError(f"Invalid output shape: {cmd.shape}, expected {(n_act,)}")
        if not np.all(np.isfinite(cmd)):
            raise ValueError("Controller output contains NaN/Inf")
        if np.any(np.abs(cmd) > max_voltage + 1e-8):
            raise ValueError("Controller output violates voltage bounds")

        applied = ACTUATOR_LAG * prev_applied + (1.0 - ACTUATOR_LAG) * cmd
        residual = (phases[i] - dm_surface_true(applied)) * pupil
        rms = float(np.sqrt(np.mean(residual[valid_mask] ** 2)))
        strehl, i_psf = shared.strehl_from_residual(residual, pupil, strehl_ref)

        rms_list.append(rms)
        strehl_list.append(strehl)
        mean_abs_u.append(float(np.mean(np.abs(cmd))))
        sparsity.append(float(np.mean(np.abs(cmd) < 1e-5)))
        prev_applied = applied

        if i == 0:
            example = {
                "phase": phases[i],
                "residual": residual,
                "psf": i_psf / (i_psf.sum() + 1e-12),
            }

    mean_rms = float(np.mean(rms_list))
    mean_strehl = float(np.mean(strehl_list))
    mean_abs_command = float(np.mean(mean_abs_u))
    mean_sparsity = float(np.mean(sparsity))
    raw_cost = float(mean_rms + ENERGY_WEIGHT * mean_abs_command)

    utilities = {
        "mean_rms": shared.utility_lower_better(
            mean_rms, SCORE_ANCHORS["mean_rms_good"], SCORE_ANCHORS["mean_rms_bad"]
        ),
        "mean_abs": shared.utility_lower_better(
            mean_abs_command, SCORE_ANCHORS["mean_abs_good"], SCORE_ANCHORS["mean_abs_bad"]
        ),
        "sparsity": shared.utility_higher_better(
            mean_sparsity, SCORE_ANCHORS["sparsity_good"], SCORE_ANCHORS["sparsity_bad"]
        ),
        "strehl": shared.utility_higher_better(
            mean_strehl, SCORE_ANCHORS["strehl_good"], SCORE_ANCHORS["strehl_bad"]
        ),
    }
    score_01 = shared.weighted_score(utilities, SCORE_WEIGHTS)

    return {
        "mean_rms": mean_rms,
        "mean_strehl": mean_strehl,
        "mean_abs_command": mean_abs_command,
        "mean_sparsity": mean_sparsity,
        "raw_cost_lower_is_better": raw_cost,
        "score_0_to_1_higher_is_better": score_01,
        "score_percent": 100.0 * score_01,
        "example": example,
    }


def build_problem(sys_cfg, scenario, max_voltage: float) -> dict:
    problem = {
        "slopes": scenario["slopes"],
        "reconstructor": sys_cfg["reconstructor"],
        "max_voltage": np.float64(max_voltage),
        "actuator_lag": np.float64(ACTUATOR_LAG),
        "n_act": np.int64(sys_cfg["n_act"]),
        "uses_prev_commands": np.int64(1),
    }
    problem.update(shared.pack_control_model(sys_cfg["control_model"]))
    return problem


def main() -> int:
    parser = argparse.ArgumentParser()
    shared.add_common_cli_args(
        parser,
        default_candidate=TASK_DIR / "baseline" / "init.py",
        default_max_voltage=0.35,
    )
    parser.add_argument("--cases", type=int, default=260)
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else VERIFICATION_DIR / "outputs"
    candidate_path = Path(args.candidate)

    sys_cfg = make_system(seed=41)
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
        sys_cfg, scenario, lambda i, s, p: commands[i], args.max_voltage
    )

    sys_cfg_ref = make_system(seed=41)
    scenario_ref = make_scenario(sys_cfg_ref, args.cases)
    reference_metrics = score_commands(
        sys_cfg_ref,
        scenario_ref,
        lambda i, s, p: reference_controller(
            s,
            sys_cfg_ref["reconstructor"],
            sys_cfg_ref["control_model"],
            p,
            max_voltage=args.max_voltage,
        ),
        args.max_voltage,
    )

    payload = {
        "task": TASK_NAME,
        "benchmark_profile": "v3_delay_and_model_mismatch",
        "candidate_module": str(candidate_path.resolve()),
        "candidate_execution": "isolated_subprocess",
        "oracle_backend": "sklearn.linear_model.Lasso + delay compensation",
        "energy_weight": ENERGY_WEIGHT,
        "actuator_lag": ACTUATOR_LAG,
        "slope_delay_noise": SLOPE_DELAY_NOISE,
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
        ["score_0_to_1_higher_is_better", "mean_rms", "mean_abs_command", "mean_sparsity"],
    )
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(json.dumps(payload, indent=2))
    print(f"Saved figures/metrics to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
