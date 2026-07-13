from __future__ import annotations

import argparse
import heapq
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
DIRS = [(-1, 0), (0, 1), (1, 0), (0, -1)]


def _write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_candidate(candidate_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("agv_candidate", candidate_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load candidate module from {candidate_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _traffic_map(entries: list[dict[str, Any]]) -> dict[tuple[int, int], float]:
    return {
        (int(item["row"]), int(item["col"])): float(item["extra_cost"])
        for item in entries
    }


def _instances() -> list[dict[str, Any]]:
    return [
        {
            "instance_id": "narrow_aisles_morning",
            "grid": [
                "..............",
                ".####..####...",
                "..............",
                "...####..####.",
                "..............",
                ".####..####...",
                "..............",
            ],
            "start": [0, 0],
            "goal": [6, 13],
            "picks": [
                {"id": 0, "row": 2, "col": 2, "priority": 1.0},
                {"id": 1, "row": 0, "col": 9, "priority": 1.3},
                {"id": 2, "row": 4, "col": 5, "priority": 0.8},
                {"id": 3, "row": 6, "col": 10, "priority": 1.1},
                {"id": 4, "row": 2, "col": 12, "priority": 0.9},
            ],
            "traffic": [
                {"row": 2, "col": 6, "extra_cost": 2.2},
                {"row": 4, "col": 7, "extra_cost": 1.8},
                {"row": 6, "col": 8, "extra_cost": 1.4},
            ],
            "turn_penalty": 0.35,
        },
        {
            "instance_id": "crossdock_afternoon",
            "grid": [
                "................",
                "..####....####..",
                "................",
                ".##..######..##.",
                "................",
                "..####....####..",
                "................",
                "....###..###....",
                "................",
            ],
            "start": [8, 0],
            "goal": [0, 15],
            "picks": [
                {"id": 0, "row": 6, "col": 3, "priority": 1.2},
                {"id": 1, "row": 2, "col": 1, "priority": 1.0},
                {"id": 2, "row": 0, "col": 6, "priority": 1.4},
                {"id": 3, "row": 4, "col": 14, "priority": 0.7},
                {"id": 4, "row": 8, "col": 11, "priority": 1.1},
                {"id": 5, "row": 2, "col": 13, "priority": 0.9},
            ],
            "traffic": [
                {"row": 4, "col": 7, "extra_cost": 2.8},
                {"row": 4, "col": 8, "extra_cost": 2.8},
                {"row": 2, "col": 8, "extra_cost": 1.5},
                {"row": 6, "col": 8, "extra_cost": 1.5},
            ],
            "turn_penalty": 0.42,
        },
        {
            "instance_id": "returns_lane_congestion",
            "grid": [
                ".............",
                ".###.###.###.",
                ".............",
                ".###.....###.",
                ".............",
                ".###.....###.",
                ".............",
                ".###.###.###.",
                ".............",
            ],
            "start": [4, 0],
            "goal": [4, 12],
            "picks": [
                {"id": 0, "row": 0, "col": 3, "priority": 0.9},
                {"id": 1, "row": 2, "col": 8, "priority": 1.2},
                {"id": 2, "row": 6, "col": 2, "priority": 0.8},
                {"id": 3, "row": 8, "col": 9, "priority": 1.1},
                {"id": 4, "row": 3, "col": 6, "priority": 1.5},
                {"id": 5, "row": 5, "col": 8, "priority": 1.0},
            ],
            "traffic": [
                {"row": 4, "col": 5, "extra_cost": 3.0},
                {"row": 4, "col": 6, "extra_cost": 3.0},
                {"row": 4, "col": 7, "extra_cost": 3.0},
                {"row": 2, "col": 6, "extra_cost": 1.2},
                {"row": 6, "col": 6, "extra_cost": 1.2},
            ],
            "turn_penalty": 0.38,
        },
    ]


def _public_instance(instance: dict[str, Any]) -> dict[str, Any]:
    grid = list(instance["grid"])
    return {
        "instance_id": instance["instance_id"],
        "rows": len(grid),
        "cols": len(grid[0]),
        "grid": grid,
        "start": list(instance["start"]),
        "goal": list(instance["goal"]),
        "picks": [dict(item) for item in instance["picks"]],
        "traffic": [dict(item) for item in instance["traffic"]],
        "turn_penalty": float(instance["turn_penalty"]),
    }


def _shortest_cost(
    grid: list[str],
    traffic: dict[tuple[int, int], float],
    start: tuple[int, int],
    goal: tuple[int, int],
    turn_penalty: float,
) -> float:
    rows = len(grid)
    cols = len(grid[0])
    pq: list[tuple[float, int, int, int]] = []
    best: dict[tuple[int, int, int], float] = {}
    for heading in range(4):
        state = (start[0], start[1], heading)
        best[state] = 0.0
        heapq.heappush(pq, (0.0, start[0], start[1], heading))

    while pq:
        cost, row, col, heading = heapq.heappop(pq)
        if cost > best.get((row, col, heading), math.inf) + 1e-12:
            continue
        if (row, col) == goal:
            return cost
        for next_heading, (dr, dc) in enumerate(DIRS):
            nr, nc = row + dr, col + dc
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
                continue
            if grid[nr][nc] == "#":
                continue
            turn_cost = 0.0 if next_heading == heading else turn_penalty
            step_cost = 1.0 + traffic.get((nr, nc), 0.0) + turn_cost
            new_cost = cost + step_cost
            key = (nr, nc, next_heading)
            if new_cost + 1e-12 < best.get(key, math.inf):
                best[key] = new_cost
                heapq.heappush(pq, (new_cost, nr, nc, next_heading))
    return math.inf


def _coerce_order(raw: Any) -> list[int]:
    if isinstance(raw, dict):
        raw = raw.get("order")
    if not isinstance(raw, (list, tuple)):
        raise ValueError("plan_order must return a list of pick ids")
    order: list[int] = []
    for item in raw:
        if isinstance(item, bool):
            raise ValueError("pick ids must be integers, not booleans")
        order.append(int(item))
    return order


def _score_instance(plan_order: Any, instance: dict[str, Any]) -> dict[str, Any]:
    public = _public_instance(instance)
    order = _coerce_order(plan_order(public))
    expected = {int(item["id"]) for item in instance["picks"]}
    if set(order) != expected or len(order) != len(expected):
        raise ValueError(
            f"invalid pick permutation for {instance['instance_id']}: expected {sorted(expected)}, got {order}"
        )

    pick_by_id = {int(item["id"]): (int(item["row"]), int(item["col"])) for item in instance["picks"]}
    stops = [tuple(instance["start"])] + [pick_by_id[item] for item in order] + [tuple(instance["goal"])]
    traffic = _traffic_map(instance["traffic"])
    total_cost = 0.0
    leg_costs: list[float] = []
    for src, dst in zip(stops, stops[1:]):
        leg = _shortest_cost(
            list(instance["grid"]),
            traffic,
            (int(src[0]), int(src[1])),
            (int(dst[0]), int(dst[1])),
            float(instance["turn_penalty"]),
        )
        if not math.isfinite(leg):
            raise ValueError(f"unreachable leg {src}->{dst} in {instance['instance_id']}")
        leg_costs.append(leg)
        total_cost += leg

    priority_weighted_lateness = 0.0
    for index, pick_id in enumerate(order):
        priority = next(float(item.get("priority", 1.0)) for item in instance["picks"] if int(item["id"]) == pick_id)
        priority_weighted_lateness += priority * index
    total_cost += 0.15 * priority_weighted_lateness
    return {
        "instance_id": instance["instance_id"],
        "order": order,
        "route_cost": total_cost,
        "leg_costs": leg_costs,
        "priority_weighted_lateness": priority_weighted_lateness,
    }


def evaluate(candidate_path: str) -> tuple[dict[str, float], dict[str, Any]]:
    module = _load_candidate(Path(candidate_path).resolve())
    plan_order = getattr(module, "plan_order", None)
    if plan_order is None:
        raise AttributeError("candidate must define plan_order(instance)")
    case_results = [_score_instance(plan_order, instance) for instance in _instances()]
    mean_cost = statistics.fmean(float(item["route_cost"]) for item in case_results)
    metrics = {
        "combined_score": -float(mean_cost),
        "valid": 1.0,
        "mean_route_cost": float(mean_cost),
        "max_route_cost": max(float(item["route_cost"]) for item in case_results),
    }
    artifacts = {
        "case_results": case_results,
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
