from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import floris
from floris import FlorisModel
import numpy as np


INVALID_SCORE = -1_000_000.0
TASK_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = TASK_ROOT / "references" / "farm_config.json"
RUNNER_PATH = TASK_ROOT / "verification" / "run_candidate.py"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a FLORIS wake-steering policy.")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--json-out", type=Path, default=Path("metrics.json"))
    parser.add_argument("--artifacts-out", type=Path, default=Path("artifacts.json"))
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _build_conditions() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    directions = np.asarray(
        [0.0, 8.0, 82.0, 90.0, 98.0, 172.0, 180.0, 188.0, 262.0, 270.0, 278.0, 352.0],
        dtype=float,
    )
    direction_weights = np.asarray(
        [0.11, 0.04, 0.07, 0.13, 0.05, 0.06, 0.12, 0.04, 0.07, 0.14, 0.05, 0.12],
        dtype=float,
    )
    speed_values = np.asarray([8.0, 10.0], dtype=float)
    speed_weights = np.asarray([0.65, 0.35], dtype=float)

    wind_directions = np.tile(directions, speed_values.size)
    wind_speeds = np.repeat(speed_values, directions.size)
    turbulence = np.repeat(np.asarray([0.06, 0.08], dtype=float), directions.size)
    frequency = np.concatenate(
        [direction_weights * speed_weight for speed_weight in speed_weights]
    )
    frequency /= frequency.sum()
    return wind_directions, wind_speeds, turbulence, frequency


def _run_candidate(
    candidate_path: Path,
    payload: dict[str, Any],
    timeout_s: float,
) -> tuple[np.ndarray, float, dict[str, Any]]:
    env = os.environ.copy()
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(RUNNER_PATH), str(candidate_path)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout_s,
        cwd=str(TASK_ROOT),
        env=env,
    )
    runtime_s = time.perf_counter() - start
    if proc.returncode != 0:
        raise RuntimeError(f"candidate runner exited with code {proc.returncode}")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("candidate runner produced no JSON result")
    result = json.loads(lines[-1])
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error", "candidate failed")))

    first = np.asarray(result["first"], dtype=float)
    second = np.asarray(result["second"], dtype=float)
    if not np.all(np.isfinite(first)) or not np.all(np.isfinite(second)):
        raise ValueError("yaw output contains NaN or infinity")
    if first.shape != second.shape or not np.array_equal(first, second):
        raise ValueError("candidate is nondeterministic for identical inputs")
    diagnostics = {
        "candidate_stdout": str(result.get("captured_stdout", ""))[-2000:],
        "candidate_stderr": str(result.get("captured_stderr", ""))[-2000:],
    }
    return first, runtime_s, diagnostics


def _smoothness(yaw: np.ndarray, wind_directions: np.ndarray, wind_speeds: np.ndarray) -> float:
    changes: list[np.ndarray] = []
    for speed in np.unique(wind_speeds):
        indices = np.where(wind_speeds == speed)[0]
        ordered = indices[np.argsort(wind_directions[indices])]
        values = yaw[ordered]
        changes.append(np.abs(np.diff(values, axis=0)))
        changes.append(np.abs(values[:1] - values[-1:]))
    if not changes:
        return 0.0
    return float(np.mean(np.concatenate([item.reshape(-1) for item in changes])))


def _invalid(error: str, runtime_s: float) -> tuple[dict[str, float], dict[str, Any]]:
    metrics = {
        "valid": 0.0,
        "combined_score": INVALID_SCORE,
        "evaluator_runtime_s": float(runtime_s),
    }
    artifacts = {"error_message": error}
    return metrics, artifacts


def evaluate(candidate_path: Path) -> tuple[dict[str, float], dict[str, Any]]:
    start = time.perf_counter()
    config = _load_config()
    if str(floris.__version__) != str(config["floris_version"]):
        return _invalid(
            f"FLORIS version mismatch: expected {config['floris_version']}, got {floris.__version__}",
            time.perf_counter() - start,
        )

    model = FlorisModel("defaults")
    rotor_diameter = float(model.core.farm.turbine_definitions[0]["rotor_diameter"])
    layout = np.asarray(config["layout_rotor_diameters"], dtype=float) * rotor_diameter
    layout_x = layout[:, 0]
    layout_y = layout[:, 1]
    wind_directions, wind_speeds, turbulence, frequency = _build_conditions()

    payload = {
        "wind_directions_deg": wind_directions.tolist(),
        "wind_speeds_mps": wind_speeds.tolist(),
        "turbulence_intensities": turbulence.tolist(),
        "layout_x_m": layout_x.tolist(),
        "layout_y_m": layout_y.tolist(),
    }

    diagnostics: dict[str, Any] = {}
    try:
        yaw, candidate_runtime_s, diagnostics = _run_candidate(
            candidate_path,
            payload,
            float(config["candidate_timeout_s"]),
        )
        expected_shape = (wind_directions.size, layout_x.size)
        if yaw.shape != expected_shape:
            raise ValueError(f"wrong yaw shape: expected {expected_shape}, got {yaw.shape}")
        if not np.all(np.isfinite(yaw)):
            raise ValueError("yaw output contains NaN or infinity")
        yaw_min = float(config["yaw_min_deg"])
        yaw_max = float(config["yaw_max_deg"])
        if float(np.min(yaw)) < yaw_min or float(np.max(yaw)) > yaw_max:
            raise ValueError(f"yaw output must stay within [{yaw_min}, {yaw_max}] degrees")

        model.set(
            layout_x=layout_x,
            layout_y=layout_y,
            wind_directions=wind_directions,
            wind_speeds=wind_speeds,
            turbulence_intensities=turbulence,
        )
        baseline_yaw = np.zeros_like(yaw)
        model.set(yaw_angles=baseline_yaw)
        model.run()
        baseline_power_by_condition = np.sum(model.get_turbine_powers(), axis=1)

        model.set(yaw_angles=yaw)
        model.run()
        candidate_power_by_condition = np.sum(model.get_turbine_powers(), axis=1)

        baseline_power = float(np.dot(frequency, baseline_power_by_condition))
        candidate_power = float(np.dot(frequency, candidate_power_by_condition))
        if not math.isfinite(candidate_power) or candidate_power <= 0.0:
            raise ValueError("FLORIS returned invalid candidate farm power")

        relative_gain_pct = 100.0 * (candidate_power / baseline_power - 1.0)
        weighted_abs_yaw = float(np.sum(frequency[:, None] * np.abs(yaw)) / yaw.shape[1])
        smoothness_deg = _smoothness(yaw, wind_directions, wind_speeds)
        effort_penalty = float(config["yaw_effort_coefficient"]) * weighted_abs_yaw
        smoothness_penalty = float(config["smoothness_coefficient"]) * smoothness_deg
        combined_score = relative_gain_pct - effort_penalty - smoothness_penalty

        metrics = {
            "valid": 1.0,
            "combined_score": float(combined_score),
            "relative_energy_gain_pct": float(relative_gain_pct),
            "baseline_expected_power_w": baseline_power,
            "candidate_expected_power_w": candidate_power,
            "weighted_mean_abs_yaw_deg": weighted_abs_yaw,
            "yaw_effort_penalty": effort_penalty,
            "yaw_smoothness_deg": smoothness_deg,
            "yaw_smoothness_penalty": smoothness_penalty,
            "candidate_runtime_s": float(candidate_runtime_s),
            "evaluator_runtime_s": float(time.perf_counter() - start),
            "n_conditions": float(wind_directions.size),
            "n_turbines": float(layout_x.size),
        }
        artifacts = {
            "summary": "candidate evaluated successfully with frozen FLORIS",
            "floris_version": str(floris.__version__),
            "turbine_model": str(config["turbine_model"]),
            "candidate_stdout": diagnostics.get("candidate_stdout", ""),
            "candidate_stderr": diagnostics.get("candidate_stderr", ""),
        }
        return metrics, artifacts
    except subprocess.TimeoutExpired:
        return _invalid(
            f"candidate exceeded {config['candidate_timeout_s']} second timeout",
            time.perf_counter() - start,
        )
    except Exception as exc:
        metrics, artifacts = _invalid(
            f"{type(exc).__name__}: {exc}",
            time.perf_counter() - start,
        )
        artifacts.update(diagnostics)
        return metrics, artifacts


def main() -> int:
    args = _parse_args()
    candidate_path = args.candidate.expanduser().resolve()
    if not candidate_path.is_file():
        metrics, artifacts = _invalid(
            f"candidate file not found: {candidate_path}",
            0.0,
        )
    else:
        metrics, artifacts = evaluate(candidate_path)
    _write_json(args.json_out, metrics)
    _write_json(args.artifacts_out, artifacts)
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
