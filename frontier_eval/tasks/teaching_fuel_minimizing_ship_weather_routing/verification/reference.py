from __future__ import annotations

import heapq
import sys
from pathlib import Path


def _ensure_repo_root() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            root = str(parent)
            if root not in sys.path:
                sys.path.insert(0, root)
            return


_ensure_repo_root()

try:
    from benchmarks.OperationsResearch.FuelMinimizingShipWeatherRouting.runtime.problem import (
        current_at,
        load_instance,
        route_metrics,
        wind_at,
    )
except ModuleNotFoundError:
    from runtime.problem import current_at, load_instance, route_metrics, wind_at


def _is_free(grid, cell):
    x, y = cell
    return 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] != "#"


def _neighbors(grid, cell):
    x, y = cell
    candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return [nxt for nxt in candidates if _is_free(grid, nxt)]


def _retrace(parent, node):
    path = []
    current = node
    while current is not None:
        path.append(current)
        current = parent[current]
    return path[::-1]


def _leg_metrics(prev, curr):
    dx = curr[0] - prev[0]
    dy = curr[1] - prev[1]
    current_u, current_v = current_at(prev)
    wind_u, wind_v = wind_at(prev)
    current_along = current_u * dx + current_v * dy
    wind_along = wind_u * dx + wind_v * dy
    headwind = max(0.0, -wind_along)
    crosswind = abs(-dy * wind_u + dx * wind_v)
    speed = max(0.35, 1.0 + 0.65 * current_along - 0.45 * headwind)
    leg_time_h = 1.0 / speed
    fuel_rate = 1.05 + 0.55 * headwind + 0.20 * crosswind + 0.25 * max(0.0, -current_along)
    leg_fuel = leg_time_h * fuel_rate
    return leg_fuel, leg_time_h


def solve(instance):
    grid = instance["grid"]
    start = instance["start"]
    goal = instance["goal"]

    frontier = [(0.0, 0.0, start)]
    parent = {start: None}
    best_cost = {start: 0.0}

    while frontier:
        cost, _, current = heapq.heappop(frontier)
        if cost != best_cost.get(current, float("inf")):
            continue
        if current == goal:
            return _retrace(parent, current)
        for nxt in _neighbors(grid, current):
            leg_fuel, _ = _leg_metrics(current, nxt)
            new_cost = cost + leg_fuel
            if new_cost < best_cost.get(nxt, float("inf")):
                best_cost[nxt] = new_cost
                parent[nxt] = current
                heapq.heappush(frontier, (new_cost, len(best_cost), nxt))
    raise RuntimeError("no feasible route found")


if __name__ == "__main__":
    instance = load_instance()
    path = solve(instance)
    print(route_metrics(path)["fuel"])
