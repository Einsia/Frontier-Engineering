"""Task A1 (constrained DM control): score a candidate that runs in its own process.

The candidate is no longer imported into this interpreter. It is launched as a
standalone script in a throwaway directory, is handed the WFS slope stream (the
observations only -- never the ground-truth phase), and returns a
``(n_cases, n_act)`` command matrix. Every metric below, including the actuator
lag recurrence the candidate had to replay on its side, is recomputed here from
those commands.

See ``benchmarks/_shared/optics_adaptive.py`` for why cutting the closed loop
this way is numerically identical to the old in-process call.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

VERIFICATION_DIR = Path(__file__).resolve().parent
TASK_DIR = VERIFICATION_DIR.parent
if str(VERIFICATION_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFICATION_DIR))


def _find_repo_root() -> Path:
    """Repo root: env var first (the sandbox relocates the benchmark tree)."""
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    raise RuntimeError("could not locate repo root for adaptive_constrained_dm_control")


_REPO = _find_repo_root()
if str(_REPO / "benchmarks" / "_shared") not in sys.path:
    sys.path.insert(0, str(_REPO / "benchmarks" / "_shared"))

# Invariant 1: every scoring dependency is resident before the candidate runs.
import optics_adaptive as shared  # noqa: E402

import aotools  # noqa: E402

from reference_controller import compute_dm_commands as reference_controller  # noqa: E402

TASK_NAME = "task1_constrained_dm_control"

SATURATION_WEIGHT = 0.5
ACTUATOR_LAG = 0.72
SLOPE_DELAY_NOISE = 0.004
PHASE_AR = 0.82

SCORE_ANCHORS = {
    "mean_rms_good": 1.35,
    "mean_rms_bad": 2.10,
    "worst_rms_good": 2.10,
    "worst_rms_bad": 3.10,
    "strehl_good": 0.24,
    "strehl_bad": 0.08,
    "sat_good": 0.02,
    "sat_bad": 0.35,
}
SCORE_WEIGHTS = {
    "mean_rms": 0.20,
    "worst_rms": 0.10,
    "strehl": 0.15,
    "saturation": 0.55,
}


def make_system(seed: int = 11):
    rng = np.random.default_rng(seed)
    sys_cfg = shared.build_optics_system(
        rng,
        plant_gain_sigma=0.14,
        plant_gain_clip=(0.68, 1.32),
    )

    h = sys_cfg["h_matrix"]
    n_act = sys_cfg["n_act"]
    normal_matrix = sys_cfg["normal_matrix"]

    # Reference oracle solves bounded ridge LS on an augmented system.
    ridge_beta = 0.5
    ridge_design_matrix = np.vstack([h, np.sqrt(ridge_beta) * np.eye(n_act)])
    ridge_rhs_zeros = np.zeros(n_act, dtype=np.float64)

    sys_cfg["modes"] = sys_cfg["zern"]
    sys_cfg["control_model"] = {
        "normal_matrix": normal_matrix,
        "h_t": h.T,
        "h_matrix": h,
        "pgd_step": 1.0 / (np.linalg.eigvalsh(normal_matrix).max() + 1e-9),
        "pgd_iters": 45,
        "ridge_beta": ridge_beta,
        "ridge_design_matrix": ridge_design_matrix,
        "ridge_rhs_zeros": ridge_rhs_zeros,
        "lag_comp_gain": 0.35,
    }
    return sys_cfg


def make_scenario(sys_cfg, n_cases: int) -> dict:
    """Draw the whole disturbance stream up front.

    Consumes ``rng`` in exactly the order the old interleaved loop did, and the
    controller never fed anything back into it, so the stream is unchanged.
    """
    rng = sys_cfg["rng"]
    pupil = sys_cfg["pupil"]
    zern = sys_cfg["modes"]
    n_pix = sys_cfg["n_pix"]
    slopes_from_phase = sys_cfg["slopes_from_phase"]
    n_slopes = sys_cfg["reconstructor"].shape[1]

    phases = np.zeros((n_cases, n_pix, n_pix), dtype=np.float64)
    slopes_stream = np.zeros((n_cases, n_slopes), dtype=np.float64)

    delayed_slopes = np.zeros(n_slopes, dtype=np.float64)
    coeff_state = rng.normal(0.0, 0.35, size=zern.shape[0])

    for i in range(n_cases):
        coeff_state = PHASE_AR * coeff_state + rng.normal(0.0, 0.22, size=zern.shape[0])
        low_order = np.tensordot(coeff_state, zern, axes=(0, 0))
        # Add a small atmospheric-like component for realism.
        r0 = float(rng.uniform(0.14, 0.24))
        l0 = float(rng.uniform(20, 50))
        high_order = aotools.ft_phase_screen(r0, n_pix, 4.2 / n_pix, l0, 0.01, seed=i + 17)
        phase = (low_order + 0.12 * high_order) * pupil

        true_slopes = slopes_from_phase(phase)
        slopes = delayed_slopes + rng.normal(0.0, SLOPE_DELAY_NOISE, size=true_slopes.shape)
        delayed_slopes = true_slopes

        phases[i] = phase
        slopes_stream[i] = slopes

    return {"phases": phases, "slopes": slopes_stream}


def score_commands(sys_cfg, scenario, get_command, max_voltage: float) -> dict:
    """Replay the plant against a command source and recompute every metric.

    ``get_command(i, slopes, prev_applied) -> np.ndarray``. The actuator lag
    recurrence lives here, so the scorer -- not the controller -- owns what was
    actually applied to the mirror.
    """
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
    sat_ratio = []
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
        sat_ratio.append(float(np.mean(np.isclose(np.abs(cmd), max_voltage, atol=1e-6))))
        prev_applied = applied

        if i == 0:
            example = {
                "phase": phases[i],
                "residual": residual,
                "psf": i_psf / (i_psf.sum() + 1e-12),
            }

    mean_rms = float(np.mean(rms_list))
    worst_rms = float(np.max(rms_list))
    mean_strehl = float(np.mean(strehl_list))
    mean_sat = float(np.mean(sat_ratio))
    raw_cost = float(mean_rms + 0.25 * worst_rms - 0.5 * mean_strehl + SATURATION_WEIGHT * mean_sat)

    utilities = {
        "mean_rms": shared.utility_lower_better(
            mean_rms, SCORE_ANCHORS["mean_rms_good"], SCORE_ANCHORS["mean_rms_bad"]
        ),
        "worst_rms": shared.utility_lower_better(
            worst_rms, SCORE_ANCHORS["worst_rms_good"], SCORE_ANCHORS["worst_rms_bad"]
        ),
        "strehl": shared.utility_higher_better(
            mean_strehl, SCORE_ANCHORS["strehl_good"], SCORE_ANCHORS["strehl_bad"]
        ),
        "saturation": shared.utility_lower_better(
            mean_sat, SCORE_ANCHORS["sat_good"], SCORE_ANCHORS["sat_bad"]
        ),
    }
    score_01 = shared.weighted_score(utilities, SCORE_WEIGHTS)

    return {
        "mean_rms": mean_rms,
        "worst_rms": worst_rms,
        "mean_strehl": mean_strehl,
        "mean_saturation_ratio": mean_sat,
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
        default_max_voltage=0.15,
    )
    parser.add_argument("--cases", type=int, default=200)
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else VERIFICATION_DIR / "outputs"
    candidate_path = Path(args.candidate)

    sys_cfg = make_system(seed=11)
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

    # Rebuild with same seed so both use exactly same scenario stream.
    sys_cfg_ref = make_system(seed=11)
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
        "oracle_backend": "scipy.optimize.lsq_linear (bounded ridge least squares)",
        "saturation_weight": SATURATION_WEIGHT,
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
        ["score_0_to_1_higher_is_better", "mean_rms", "mean_strehl", "mean_saturation_ratio"],
    )
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(json.dumps(payload, indent=2))
    print(f"Saved figures/metrics to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
