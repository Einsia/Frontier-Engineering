from __future__ import annotations

from collections import deque
from heapq import heappop, heappush
from typing import Any


GRID = (
    "##########",
    "#....#..##",
    "#..#..#.##",
    "#..B##.bC#",
    "#...c#...#",
    "#......#A#",
    "#.a..#...#",
    "##########",
)
BASELINE_ORDER = (0, 1, 2)


def _parse_grid():
    start_map: dict[str, tuple[int, int]] = {}
    goal_map: dict[str, tuple[int, int]] = {}
    rows = []
    for y, row in enumerate(GRID):
        new_row = []
        for x, cell in enumerate(row):
            if cell in "ABC":
                start_map[cell] = (x, y)
                new_row.append(".")
            elif cell in "abc":
                goal_map[cell.upper()] = (x, y)
                new_row.append(".")
            else:
                new_row.append(cell)
        rows.append("".join(new_row))
    robot_ids = tuple(sorted(start_map))
    starts = tuple(start_map[robot_id] for robot_id in robot_ids)
    goals = tuple(goal_map[robot_id] for robot_id in robot_ids)
    return tuple(rows), robot_ids, starts, goals


FREE_GRID, ROBOT_IDS, STARTS, GOALS = _parse_grid()


def load_instance() -> dict[str, Any]:
    return {"grid": FREE_GRID, "robot_ids": ROBOT_IDS, "starts": STARTS, "goals": GOALS}


def _to_cell(value: Any) -> tuple[int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("cell must be a length-2 sequence")
    return int(round(float(value[0]))), int(round(float(value[1])))


def _extract_paths(value: Any) -> list[list[tuple[int, int]]]:
    if isinstance(value, dict):
        if "paths" not in value:
            raise ValueError("missing paths")
        value = value["paths"]
    paths = []
    for raw_path in value:
        path = [_to_cell(cell) for cell in raw_path]
        if not path:
            raise ValueError("robot path is empty")
        paths.append(path)
    if len(paths) != len(STARTS):
        raise ValueError("incorrect number of robot paths")
    return paths


def is_free(cell: tuple[int, int]) -> bool:
    x, y = cell
    return 0 <= y < len(FREE_GRID) and 0 <= x < len(FREE_GRID[0]) and FREE_GRID[y][x] != "#"


def neighbors(cell: tuple[int, int], allow_wait: bool = False) -> list[tuple[int, int]]:
    x, y = cell
    result = []
    candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    if allow_wait:
        candidates.append((x, y))
    for candidate in candidates:
        if is_free(candidate):
            result.append(candidate)
    return result


def _retrace(parent: dict[tuple[tuple[int, int], int], tuple[tuple[int, int], int] | None], node: tuple[tuple[int, int], int]) -> list[tuple[int, int]]:
    path = []
    current = node
    while current is not None:
        path.append(current[0])
        current = parent[current]
    return path[::-1]


def breadth_first_shortest_path(start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]] | None:
    queue = deque([start])
    parent = {start: None}
    while queue:
        current = queue.popleft()
        if current == goal:
            out = []
            node = current
            while node is not None:
                out.append(node)
                node = parent[node]
            return out[::-1]
        for nxt in neighbors(current, allow_wait=False):
            if nxt not in parent:
                parent[nxt] = current
                queue.append(nxt)
    return None


def space_time_astar(
    start: tuple[int, int],
    goal: tuple[int, int],
    reserved_vertices: set[tuple[tuple[int, int], int]],
    reserved_edges: set[tuple[tuple[tuple[int, int], tuple[int, int]], int]],
    max_time: int = 40,
) -> list[tuple[int, int]] | None:
    def heuristic(cell: tuple[int, int]) -> int:
        return abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])

    frontier = [(heuristic(start), 0, start)]
    parent = {(start, 0): None}
    best_time = {(start, 0): 0}
    while frontier:
        _, current_time, current = heappop(frontier)
        if best_time[(current, current_time)] != current_time:
            continue
        if current == goal:
            return _retrace(parent, (current, current_time))
        if current_time >= max_time:
            continue
        for nxt in neighbors(current, allow_wait=True):
            next_time = current_time + 1
            if (nxt, next_time) in reserved_vertices:
                continue
            if ((current, nxt), next_time) in reserved_edges:
                continue
            if ((nxt, current), next_time) in reserved_edges:
                continue
            state = (nxt, next_time)
            if state in best_time and next_time >= best_time[state]:
                continue
            best_time[state] = next_time
            parent[state] = (current, current_time)
            heappush(frontier, (next_time + heuristic(nxt), next_time, nxt))
    return None


def reserve_path(
    path: list[tuple[int, int]],
    reserved_vertices: set[tuple[tuple[int, int], int]],
    reserved_edges: set[tuple[tuple[tuple[int, int], tuple[int, int]], int]],
    horizon: int = 40,
) -> None:
    for t, cell in enumerate(path):
        reserved_vertices.add((cell, t))
        if t > 0:
            reserved_edges.add(((path[t - 1], cell), t))
        if t == len(path) - 1:
            for future in range(t + 1, horizon + 1):
                reserved_vertices.add((cell, future))


def prioritized_plan(order: tuple[int, ...]) -> list[list[tuple[int, int]]] | None:
    reserved_vertices: set[tuple[tuple[int, int], int]] = set()
    reserved_edges: set[tuple[tuple[tuple[int, int], tuple[int, int]], int]] = set()
    paths: list[list[tuple[int, int]] | None] = [None] * len(STARTS)
    for robot_idx in order:
        path = space_time_astar(STARTS[robot_idx], GOALS[robot_idx], reserved_vertices, reserved_edges)
        if path is None:
            return None
        paths[robot_idx] = path
        reserve_path(path, reserved_vertices, reserved_edges)
    return [path for path in paths if path is not None]


def baseline_plan_paths() -> list[list[tuple[int, int]]]:
    result = prioritized_plan(tuple(BASELINE_ORDER))
    if result is None:
        raise RuntimeError("baseline prioritized planner failed")
    return result


def validate_paths(value: Any) -> list[list[tuple[int, int]]]:
    paths = _extract_paths(value)
    for idx, path in enumerate(paths):
        if path[0] != STARTS[idx]:
            raise ValueError(f"robot {idx} path does not start at the correct cell")
        if path[-1] != GOALS[idx]:
            raise ValueError(f"robot {idx} path does not end at the correct cell")
        for cell in path:
            if not is_free(cell):
                raise ValueError("robot path enters an obstacle or leaves the grid")
        for previous, current in zip(path, path[1:]):
            dx = abs(previous[0] - current[0])
            dy = abs(previous[1] - current[1])
            if dx + dy not in {0, 1}:
                raise ValueError("robot path contains a non-adjacent move")

    horizon = max(len(path) for path in paths)
    previous_positions = [path[0] for path in paths]
    for t in range(horizon):
        positions = [path[t] if t < len(path) else path[-1] for path in paths]
        if len(set(positions)) != len(positions):
            raise ValueError("vertex collision detected")
        if t > 0:
            for i in range(len(paths)):
                for j in range(i + 1, len(paths)):
                    if previous_positions[i] == positions[j] and previous_positions[j] == positions[i]:
                        raise ValueError("edge-swap collision detected")
        previous_positions = positions
    return paths


def total_cost(value: Any) -> int:
    return sum(len(path) - 1 for path in validate_paths(value))


def makespan(value: Any) -> int:
    return max(len(path) - 1 for path in validate_paths(value))


LOWER_BOUND_TOTAL_COST = 0
for start, goal in zip(STARTS, GOALS):
    shortest = breadth_first_shortest_path(start, goal)
    if shortest is None:
        raise RuntimeError("a robot has no individual shortest path")
    LOWER_BOUND_TOTAL_COST += len(shortest) - 1
