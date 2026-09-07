"""Task A2 (temporally smooth DM control): score a candidate that runs alone.

The candidate is launched as a standalone script in a scratch directory. It gets
the episodic WFS slope stream (observations only, never the ground-truth phase)
and returns one command matrix of shape ``(episodes * steps, n_act)``. This
process then re-runs the rate limiter, the actuator lag and every metric on its
own copy of the plant, so nothing the candidate believes about its own state can
move the score.
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
    raise RuntimeError("could not locate repo root for adaptive_temporal_smooth_control")


_REPO = _find_repo_root()
if str(_REPO / "benchmarks" / "_shared") not in sys.path:
    sys.path.insert(0, str(_REPO / "benchmarks" / "_shared"))

# Invariant 1: every scoring dependency is resident before the candidate runs.
import optics_adaptive as shared  # noqa: E402

from reference_controller import compute_dm_commands as reference_controller  # noqa: E402

TASK_NAME = "task2_temporal_smooth_control"

SLEW_WEIGHT = 5.2
ACTUATOR_LAG = 0.76
SLOPE_DELAY_NOISE = 0.004
ACTUATOR_RATE_LIMIT = 0.055

SCORE_ANCHORS = {
    "mean_rms_good": 1.45,
    "mean_rms_bad": 2.10,
    "mean_slew_good": 0.045,
    "mean_slew_bad": 0.19,
    "strehl_good": 0.24,
    "strehl_bad": 0.10,
}
SCORE_WEIGHTS = {
    "mean_rms": 0.20,
    "mean_slew": 0.65,
    "strehl": 0.15,
}


def make_system(seed: int = 29):
    rng = np.random.default_rng(seed)
    sys_cfg = shared.build_optics_system(
        rng,
        plant_gain_sigma=0.16,
        plant_gain_clip=(0.66, 1.34),
    )

    h = sys_cfg["h_matrix"]
    g = sys_cfg["gram"]
    n_act = sys_cfg["n_act"]

    smooth_beta = 18.0
    inv_smooth = np.linalg.inv(g + smooth_beta * np.eye(n_act))
    smooth_reconstructor = inv_smooth @ h.T
    prev_blend = inv_smooth @ (smooth_beta * np.eye(n_act))

    sys_cfg["ar_alpha"] = np.linspace(0.65, 0.40, sys_cfg["zern"].shape[0])
    sys_cfg["control_model"] = {
        "smooth_reconstructor": smooth_reconstructor,
        "prev_blend": prev_blend,
        "reconstructor": sys_cfg["reconstructor"],
        "delay_prediction_gain": 0.55,
        "command_lowpass": 0.88,
    }
    return sys_cfg


def make_scenario(sys_cfg, episodes: int, steps: int) -> dict:
    """Draw every episode's disturbance stream before any controller runs.

    Stores the modal coefficients rather than the 96x96 phase maps (2520 frames
    would be ~185 MB); the phase is regenerated from them during scoring with the
    identical ``tensordot``.
    """
    rng = sys_cfg["rng"]
    zern = sys_cfg["zern"]
    alpha = sys_cfg["ar_alpha"]
    slopes_from_phase = sys_cfg["slopes_from_phase"]
    n_slopes = sys_cfg["reconstructor"].shape[1]
    n_modes = zern.shape[0]

    total = episodes * steps
    coeffs = np.zeros((total, n_modes), dtype=np.float64)
    slopes_stream = np.zeros((total, n_slopes), dtype=np.float64)

    for ep in range(episodes):
        coeff = rng.normal(0.0, 0.6, size=n_modes)
        delayed_slopes = np.zeros(n_slopes, dtype=np.float64)
        for t in range(steps):
            coeff = alpha * coeff + rng.normal(0.0, 0.35, size=coeff.shape)
            phase = np.tensordot(coeff, zern, axes=(0, 0))

            true_slopes = slopes_from_phase(phase)
            slopes = delayed_slopes + rng.normal(0.0, SLOPE_DELAY_NOISE, size=true_slopes.shape)
            delayed_slopes = true_slopes

            idx = ep * steps + t
            coeffs[idx] = coeff
            slopes_stream[idx] = slopes

    return {"coeffs": coeffs, "slopes": slopes_stream, "episodes": episodes, "steps": steps}


def score_commands(sys_cfg, scenario, get_command, max_voltage: float) -> dict:
    """Replay rate limiter + actuator lag against a command source and re-score."""
    pupil = sys_cfg["pupil"]
    valid_mask = sys_cfg["valid_mask"]
    zern = sys_cfg["zern"]
    dm_surface_true = sys_cfg["dm_surface_true"]
    strehl_ref = sys_cfg["strehl_ref"]
    n_act = sys_cfg["n_act"]

    coeffs = scenario["coeffs"]
    slopes_stream = scenario["slopes"]
    episodes = scenario["episodes"]
    steps = scenario["steps"]

    rms_list = []
    strehl_list = []
    slew_list = []
    example = None

    for ep in range(episodes):
        prev_applied = np.zeros(n_act, dtype=np.float64)
        prev_cmd = np.zeros(n_act, dtype=np.float64)

        for t in range(steps):
            idx = ep * steps + t
            phase = np.tensordot(coeffs[idx], zern, axes=(0, 0))

            cmd = np.asarray(get_command(idx, slopes_stream[idx], prev_applied), dtype=np.float64)

            if cmd.shape != (n_act,):
                raise ValueError(f"Invalid output shape: {cmd.shape}, expected {(n_act,)}")
            if not np.all(np.isfinite(cmd)):
                raise ValueError("Controller output contains NaN/Inf")
            if np.any(np.abs(cmd) > max_voltage + 1e-8):
                raise ValueError("Controller output violates voltage bounds")

            delta_cmd = np.clip(cmd - prev_applied, -ACTUATOR_RATE_LIMIT, ACTUATOR_RATE_LIMIT)
            limited_cmd = prev_applied + delta_cmd
            applied = ACTUATOR_LAG * prev_applied + (1.0 - ACTUATOR_LAG) * limited_cmd
            residual = (phase - dm_surface_true(applied)) * pupil
            rms = float(np.sqrt(np.mean(residual[valid_mask] ** 2)))
            strehl, i_psf = shared.strehl_from_residual(residual, pupil, strehl_ref)
            slew = float(np.mean(np.abs(cmd - prev_cmd)))

            rms_list.append(rms)
            strehl_list.append(strehl)
            slew_list.append(slew)

            if ep == 0 and t == 0:
                example = {
                    "phase": phase,
                    "residual": residual,
                    "psf": i_psf / (i_psf.sum() + 1e-12),
                }

            prev_cmd = cmd
            prev_applied = applied

    mean_rms = float(np.mean(rms_list))
    mean_strehl = float(np.mean(strehl_list))
    mean_slew = float(np.mean(slew_list))
    raw_cost = float(mean_rms + SLEW_WEIGHT * mean_slew)

    utilities = {
        "mean_rms": shared.utility_lower_better(
            mean_rms, SCORE_ANCHORS["mean_rms_good"], SCORE_ANCHORS["mean_rms_bad"]
        ),
        "mean_slew": shared.utility_lower_better(
            mean_slew, SCORE_ANCHORS["mean_slew_good"], SCORE_ANCHORS["mean_slew_bad"]
        ),
        "strehl": shared.utility_higher_better(
            mean_strehl, SCORE_ANCHORS["strehl_good"], SCORE_ANCHORS["strehl_bad"]
        ),
    }
    score_01 = shared.weighted_score(utilities, SCORE_WEIGHTS)

    return {
        "mean_rms": mean_rms,
        "mean_strehl": mean_strehl,
        "mean_slew": mean_slew,
        "raw_cost_lower_is_better": raw_cost,
        "score_0_to_1_higher_is_better": score_01,
        "score_percent": 100.0 * score_01,
        "example": example,
    }


def build_problem(sys_cfg, scenario, max_voltage: float) -> dict:
    """Exactly what the candidate subprocess is allowed to see."""
    problem = {
        "slopes": scenario["slopes"],
        "reconstructor": sys_cfg["reconstructor"],
        "max_voltage": np.float64(max_voltage),
        "actuator_lag": np.float64(ACTUATOR_LAG),
        "rate_limit": np.float64(ACTUATOR_RATE_LIMIT),
        "episode_length": np.int64(scenario["steps"]),
        "n_episodes": np.int64(scenario["episodes"]),
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
        default_max_voltage=0.25,
    )
    parser.add_argument("--episodes", type=int, default=36)
    parser.add_argument("--steps", type=int, default=70)
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else VERIFICATION_DIR / "outputs"
    candidate_path = Path(args.candidate)

    sys_cfg = make_system(seed=29)
    scenario = make_scenario(sys_cfg, args.episodes, args.steps)

    try:
        commands = shared.run_candidate_controller(
            candidate_path,
            problem=build_problem(sys_cfg, scenario, args.max_voltage),
            n_steps=args.episodes * args.steps,
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

    sys_cfg_ref = make_system(seed=29)
    scenario_ref = make_scenario(sys_cfg_ref, args.episodes, args.steps)
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
        "oracle_backend": "delay-compensated analytical smooth controller",
        "slew_weight": SLEW_WEIGHT,
        "actuator_lag": ACTUATOR_LAG,
        "actuator_rate_limit": ACTUATOR_RATE_LIMIT,
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
        ["score_0_to_1_higher_is_better", "mean_rms", "mean_slew", "mean_strehl"],
    )
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(json.dumps(payload, indent=2))
    print(f"Saved figures/metrics to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
