from __future__ import annotations

from collections import deque
import math
from typing import Any


WIDTH = 20
HEIGHT = 10
START = (1, 4)
GOAL = (18, 4)


def is_land(cell: tuple[int, int]) -> bool:
    x, y = cell
    return 8 <= x <= 12 and 2 <= y <= 6


def is_water(cell: tuple[int, int]) -> bool:
    x, y = cell
    return 0 <= x < WIDTH and 0 <= y < HEIGHT and not is_land(cell)


def _render_grid() -> tuple[str, ...]:
    rows = []
    for y in range(HEIGHT):
        chars = []
        for x in range(WIDTH):
            cell = (x, y)
            if cell == START:
                chars.append("S")
            elif cell == GOAL:
                chars.append("G")
            elif is_land(cell):
                chars.append("#")
            else:
                chars.append(".")
        rows.append("".join(chars))
    return tuple(rows)


GRID = _render_grid()


def current_at(cell: tuple[int, int]) -> tuple[float, float]:
    x, y = cell
    east = 0.04 * math.sin(0.45 * x)
    north = 0.02 * math.cos(0.35 * x)
    if y <= 2:
        return (-0.32 + east, north)
    if y >= 6:
        return (0.26 + east, -north)
    return (0.04 + east, 0.01 * math.sin(0.25 * x))


def wind_at(cell: tuple[int, int]) -> tuple[float, float]:
    x, y = cell
    side = 0.04 * math.sin(0.3 * x)
    if y <= 2:
        return (-0.60, side)
    if y >= 6:
        return (0.22, -side)
    return (-0.08, 0.02 * math.cos(0.2 * x))


def _field_to_rows(field_fn) -> tuple[tuple[tuple[float, float], ...], ...]:
    rows = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            row.append(tuple(round(v, 4) for v in field_fn((x, y))))
        rows.append(tuple(row))
    return tuple(rows)


CURRENT_FIELD = _field_to_rows(current_at)
WIND_FIELD = _field_to_rows(wind_at)


def load_instance() -> dict[str, Any]:
    return {
        "grid": GRID,
        "start": START,
        "goal": GOAL,
        "current_field": CURRENT_FIELD,
        "wind_field": WIND_FIELD,
        "objective": "fuel",
    }


def _to_cell(value: Any) -> tuple[int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("cell must be a length-2 sequence")
    return int(round(float(value[0]))), int(round(float(value[1])))


def extract_path(value: Any) -> list[tuple[int, int]]:
    if isinstance(value, dict):
        if "path" not in value:
            raise ValueError("missing path")
        value = value["path"]
    path = [_to_cell(cell) for cell in value]
    if not path:
        raise ValueError("path is empty")
    return path


def neighbors(cell: tuple[int, int], directions=((0, -1), (1, 0), (0, 1), (-1, 0))) -> list[tuple[int, int]]:
    x, y = cell
    result = []
    for dx, dy in directions:
        nxt = (x + dx, y + dy)
        if is_water(nxt):
            result.append(nxt)
    return result


def validate_path(value: Any) -> list[tuple[int, int]]:
    path = extract_path(value)
    if path[0] != START:
        raise ValueError("path must start at START")
    if path[-1] != GOAL:
        raise ValueError("path must end at GOAL")
    for cell in path:
        if not is_water(cell):
            raise ValueError("path enters land or leaves the map")
    for prev, curr in zip(path, path[1:]):
        dx = abs(curr[0] - prev[0])
        dy = abs(curr[1] - prev[1])
        if dx + dy != 1:
            raise ValueError("path contains a non-adjacent move")
    return path


def _leg_metrics(prev: tuple[int, int], curr: tuple[int, int]) -> tuple[float, float]:
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


def route_metrics(value: Any) -> dict[str, float]:
    path = validate_path(value)
    total_fuel = 0.0
    total_time_h = 0.0
    for prev, curr in zip(path, path[1:]):
        leg_fuel, leg_time_h = _leg_metrics(prev, curr)
        total_fuel += leg_fuel
        total_time_h += leg_time_h
    return {
        "fuel": float(total_fuel),
        "time_h": float(total_time_h),
        "hops": float(len(path) - 1),
    }


def _retrace(parent, node):
    path = []
    current = node
    while current is not None:
        path.append(current)
        current = parent[current]
    return path[::-1]


def baseline_path() -> list[tuple[int, int]]:
    queue = deque([START])
    parent = {START: None}
    while queue:
        current = queue.popleft()
        if current == GOAL:
            return _retrace(parent, current)
        for nxt in neighbors(current):
            if nxt not in parent:
                parent[nxt] = current
                queue.append(nxt)
    raise RuntimeError("baseline path not found")


BASELINE_PATH = baseline_path()
BASELINE_FUEL = route_metrics(BASELINE_PATH)["fuel"]
BASELINE_TIME_H = route_metrics(BASELINE_PATH)["time_h"]
REFERENCE_FUEL = 21.839377308460037
REFERENCE_TIME_H = 20.501439186435814
