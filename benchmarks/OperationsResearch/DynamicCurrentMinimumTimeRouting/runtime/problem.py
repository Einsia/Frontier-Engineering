from __future__ import annotations

from collections import deque
import math
from typing import Any


WIDTH = 20
HEIGHT = 10
START = (1, 4)
GOAL = (18, 4)
MIN_DEPTH = 2.5


def is_land(cell: tuple[int, int]) -> bool:
    x, y = cell
    return 8 <= x <= 12 and 2 <= y <= 6


def depth_at(cell: tuple[int, int]) -> float:
    x, y = cell
    if is_land(cell):
        return 0.0
    depth = 3.8
    if y == 1 and 7 <= x <= 13:
        depth = 2.7
    if y == 6 and 2 <= x <= 5:
        depth = 2.2
    if y == 7 and 3 <= x <= 6:
        depth = 2.4
    return depth


def is_navigable(cell: tuple[int, int]) -> bool:
    x, y = cell
    return 0 <= x < WIDTH and 0 <= y < HEIGHT and not is_land(cell) and depth_at(cell) >= MIN_DEPTH


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
            elif depth_at(cell) < MIN_DEPTH:
                chars.append("~")
            else:
                chars.append(".")
        rows.append("".join(chars))
    return tuple(rows)


GRID = _render_grid()


def current_at(cell: tuple[int, int]) -> tuple[float, float]:
    x, y = cell
    ripple = 0.03 * math.sin(0.4 * x)
    if y <= 2:
        return (-0.36 + ripple, 0.01 * math.cos(0.3 * x))
    if y >= 7:
        return (0.44 + ripple, -0.01 * math.cos(0.3 * x))
    return (-0.05 + ripple, 0.02 * math.sin(0.2 * x))


def _field_to_rows(field_fn) -> tuple[tuple[Any, ...], ...]:
    rows = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            value = field_fn((x, y))
            if isinstance(value, tuple):
                row.append(tuple(round(v, 4) for v in value))
            else:
                row.append(round(float(value), 4))
        rows.append(tuple(row))
    return tuple(rows)


CURRENT_FIELD = _field_to_rows(current_at)
DEPTH_FIELD = _field_to_rows(depth_at)


def load_instance() -> dict[str, Any]:
    return {
        "grid": GRID,
        "start": START,
        "goal": GOAL,
        "current_field": CURRENT_FIELD,
        "depth_field": DEPTH_FIELD,
        "min_depth": MIN_DEPTH,
        "objective": "time",
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
        if is_navigable(nxt):
            result.append(nxt)
    return result


def validate_path(value: Any) -> list[tuple[int, int]]:
    path = extract_path(value)
    if path[0] != START:
        raise ValueError("path must start at START")
    if path[-1] != GOAL:
        raise ValueError("path must end at GOAL")
    for cell in path:
        if not is_navigable(cell):
            raise ValueError("path enters land, leaves the map, or violates minimum depth")
    for prev, curr in zip(path, path[1:]):
        dx = abs(curr[0] - prev[0])
        dy = abs(curr[1] - prev[1])
        if dx + dy != 1:
            raise ValueError("path contains a non-adjacent move")
    return path


def _leg_time(prev: tuple[int, int], curr: tuple[int, int]) -> float:
    dx = curr[0] - prev[0]
    dy = curr[1] - prev[1]
    current_u, current_v = current_at(prev)
    current_along = current_u * dx + current_v * dy
    depth = depth_at(curr)
    shallow_penalty = max(0.0, 3.0 - depth) * 0.22
    speed = max(0.25, 1.0 + 0.9 * current_along - shallow_penalty)
    return 1.0 / speed


def route_metrics(value: Any) -> dict[str, float]:
    path = validate_path(value)
    total_time_h = 0.0
    for prev, curr in zip(path, path[1:]):
        total_time_h += _leg_time(prev, curr)
    return {
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
BASELINE_TIME_H = route_metrics(BASELINE_PATH)["time_h"]
BASELINE_HOPS = route_metrics(BASELINE_PATH)["hops"]
REFERENCE_TIME_H = 20.012194145529936
REFERENCE_HOPS = 23.0
