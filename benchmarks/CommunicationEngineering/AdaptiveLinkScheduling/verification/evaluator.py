from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
import time
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any


INVALID_COMBINED_SCORE = -1e18
MCS_TABLE = [
    {"mcs": 0, "snr_threshold_db": -3.0, "bits_per_rb": 180.0},
    {"mcs": 1, "snr_threshold_db": 1.0, "bits_per_rb": 300.0},
    {"mcs": 2, "snr_threshold_db": 4.0, "bits_per_rb": 480.0},
    {"mcs": 3, "snr_threshold_db": 8.0, "bits_per_rb": 720.0},
    {"mcs": 4, "snr_threshold_db": 12.0, "bits_per_rb": 960.0},
    {"mcs": 5, "snr_threshold_db": 16.0, "bits_per_rb": 1200.0},
]


def _write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_candidate(candidate_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("link_scheduler_candidate", candidate_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load candidate module from {candidate_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frames() -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for frame_id in range(18):
        num_rbs = 12
        users: list[dict[str, Any]] = []
        for user_id in range(5):
            queue = 1100.0 + 260.0 * ((frame_id + 2 * user_id) % 5) + 180.0 * math.sin(0.6 * frame_id + user_id)
            latency = 0.8 + 0.25 * ((2 * user_id + frame_id) % 4)
            min_service = 360.0 + 120.0 * ((user_id + frame_id) % 3)
            snrs: list[float] = []
            for rb in range(num_rbs):
                slow = 7.5 + 5.0 * math.sin(0.37 * frame_id + 0.73 * user_id)
                selective = 4.3 * math.cos(0.61 * rb + 0.41 * user_id + 0.19 * frame_id)
                edge_loss = -2.0 if user_id == 4 and frame_id % 3 == 1 else 0.0
                snrs.append(slow + selective + edge_loss)
            users.append(
                {
                    "id": user_id,
                    "queue_bits": max(250.0, queue),
                    "latency_weight": latency,
                    "min_service_bits": min_service,
                    "snr_estimate_db": snrs,
                }
            )
        frames.append(
            {
                "frame_id": f"frame_{frame_id:02d}",
                "num_resource_blocks": num_rbs,
                "mcs_table": [dict(item) for item in MCS_TABLE],
                "power_min_dbm": 5.0,
                "power_max_dbm": 24.0,
                "power_budget_mw": 1450.0,
                "implementation_margin_db": 1.25,
                "users": users,
            }
        )
    return frames


def _mcs_by_id() -> dict[int, dict[str, float]]:
    return {int(item["mcs"]): dict(item) for item in MCS_TABLE}


def _dbm_to_mw(power_dbm: float) -> float:
    return 10.0 ** (power_dbm / 10.0)


def _coerce_decision(raw: Any) -> tuple[int, int, float]:
    if not isinstance(raw, dict):
        raise ValueError("each schedule entry must be a dict")
    user = int(raw["user"])
    mcs = int(raw["mcs"])
    power = float(raw["power_dbm"])
    if not math.isfinite(power):
        raise ValueError("power_dbm must be finite")
    return user, mcs, power


def _public_frame(frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "frame_id": frame["frame_id"],
        "num_resource_blocks": frame["num_resource_blocks"],
        "mcs_table": [dict(item) for item in frame["mcs_table"]],
        "power_min_dbm": frame["power_min_dbm"],
        "power_max_dbm": frame["power_max_dbm"],
        "power_budget_mw": frame["power_budget_mw"],
        "users": [
            {
                "id": user["id"],
                "queue_bits": user["queue_bits"],
                "latency_weight": user["latency_weight"],
                "min_service_bits": user["min_service_bits"],
                "snr_estimate_db": list(user["snr_estimate_db"]),
            }
            for user in frame["users"]
        ],
    }


def _jain(values: list[float]) -> float:
    if not values:
        return 0.0
    total = sum(values)
    sq = sum(v * v for v in values)
    if sq <= 0.0:
        return 0.0
    return total * total / (len(values) * sq)


def _score_frame(schedule_frame: Any, frame: dict[str, Any]) -> dict[str, Any]:
    public = _public_frame(frame)
    raw_schedule = schedule_frame(public)
    if not isinstance(raw_schedule, (list, tuple)):
        raise ValueError("schedule_frame must return a list")
    if len(raw_schedule) != int(frame["num_resource_blocks"]):
        raise ValueError(
            f"expected {frame['num_resource_blocks']} decisions, got {len(raw_schedule)}"
        )

    mcs_lookup = _mcs_by_id()
    users = {int(user["id"]): dict(user) for user in frame["users"]}
    remaining = {user_id: float(user["queue_bits"]) for user_id, user in users.items()}
    delivered = {user_id: 0.0 for user_id in users}
    weighted_kbits = 0.0
    power_mw_total = 0.0
    outage_count = 0
    invalid_penalty = 0.0

    for rb, raw in enumerate(raw_schedule):
        try:
            user_id, mcs_id, power_dbm = _coerce_decision(raw)
        except Exception:
            invalid_penalty += 20.0
            continue
        if user_id not in users or mcs_id not in mcs_lookup:
            invalid_penalty += 20.0
            continue

        clipped_power = max(float(frame["power_min_dbm"]), min(float(frame["power_max_dbm"]), power_dbm))
        invalid_penalty += abs(power_dbm - clipped_power) * 0.5
        power_dbm = clipped_power
        power_mw = _dbm_to_mw(power_dbm)
        power_mw_total += power_mw

        user = users[user_id]
        mcs = mcs_lookup[mcs_id]
        effective_snr = float(user["snr_estimate_db"][rb]) + (power_dbm - 20.0)
        threshold = float(mcs["snr_threshold_db"]) + float(frame["implementation_margin_db"])
        if effective_snr + 1e-9 < threshold:
            outage_count += 1
            continue

        bits = min(float(mcs["bits_per_rb"]), remaining[user_id])
        if bits <= 0.0:
            continue
        remaining[user_id] -= bits
        delivered[user_id] += bits
        weighted_kbits += float(user["latency_weight"]) * bits / 1000.0

    service_bonus = 0.0
    service_shortfall = 0.0
    for user_id, user in users.items():
        target = float(user["min_service_bits"])
        got = delivered[user_id]
        service_bonus += min(got, target) / 1000.0
        service_shortfall += max(0.0, target - got) / 1000.0

    fairness = _jain([delivered[user_id] for user_id in sorted(delivered)])
    budget_excess = max(0.0, power_mw_total - float(frame["power_budget_mw"]))
    utility = (
        weighted_kbits
        + 1.25 * service_bonus
        + 3.5 * fairness
        - 0.0018 * power_mw_total
        - 0.010 * budget_excess
        - 0.85 * outage_count
        - 1.7 * service_shortfall
        - invalid_penalty
    )
    return {
        "frame_id": frame["frame_id"],
        "utility": utility,
        "delivered_bits_total": sum(delivered.values()),
        "power_mw_total": power_mw_total,
        "outage_count": outage_count,
        "fairness": fairness,
        "service_shortfall_kbits": service_shortfall,
        "invalid_penalty": invalid_penalty,
        "delivered_by_user": delivered,
    }


def evaluate(candidate_path: str) -> tuple[dict[str, float], dict[str, Any]]:
    module = _load_candidate(Path(candidate_path).resolve())
    schedule_frame = getattr(module, "schedule_frame", None)
    if schedule_frame is None:
        raise AttributeError("candidate must define schedule_frame(frame)")
    frame_results = [_score_frame(schedule_frame, frame) for frame in _frames()]
    mean_utility = statistics.fmean(float(item["utility"]) for item in frame_results)
    mean_bits = statistics.fmean(float(item["delivered_bits_total"]) for item in frame_results)
    mean_outages = statistics.fmean(float(item["outage_count"]) for item in frame_results)
    metrics = {
        "combined_score": float(mean_utility),
        "valid": 1.0,
        "mean_frame_utility": float(mean_utility),
        "mean_delivered_bits": float(mean_bits),
        "mean_outage_count": float(mean_outages),
    }
    artifacts = {
        "frame_results": frame_results,
        "score_direction": "higher_is_better",
    }
    return metrics, artifacts


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate")
    parser.add_argument("--metrics-out", default="metrics.json")
    parser.add_argument("--artifacts-out", default="artifacts.json")
    args = parser.parse_args(argv)

    start = time.time()
    try:
        metrics, artifacts = evaluate(args.candidate)
    except Exception as exc:
        metrics = {
            "combined_score": INVALID_COMBINED_SCORE,
            "valid": 0.0,
            "runtime_s": float(time.time() - start),
        }
        artifacts = {
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
        }
    metrics["runtime_s"] = float(time.time() - start)
    artifacts["candidate_path"] = str(Path(args.candidate).resolve())
    _write_json(args.metrics_out, metrics)
    _write_json(args.artifacts_out, artifacts)
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
