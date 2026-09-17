from __future__ import annotations

from collections import deque
from pathlib import Path
import sys


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _ensure_repo_root() -> None:
    root = str(_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)


_ensure_repo_root()

from benchmarks.Robotics.MultiRobotPrioritizedPlanning.runtime import problem as benchmark_problem


def _is_free(grid: tuple[str, ...], cell: tuple[int, int]) -> bool:
    x, y = cell
    return 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] != "#"


def _neighbors(grid: tuple[str, ...], cell: tuple[int, int]) -> list[tuple[int, int]]:
    x, y = cell
    candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1), (x, y)]
    return [candidate for candidate in candidates if _is_free(grid, candidate)]


def _shortest_path_length(grid: tuple[str, ...], start: tuple[int, int], goal: tuple[int, int]) -> int:
    queue = deque([start])
    distance = {start: 0}
    while queue:
        current = queue.popleft()
        if current == goal:
            return distance[current]
        for nxt in _neighbors(grid, current):
            if nxt not in distance:
                distance[nxt] = distance[current] + 1
                queue.append(nxt)
    raise RuntimeError("no individual path exists")


def _space_time_bfs(
    grid: tuple[str, ...],
    start: tuple[int, int],
    goal: tuple[int, int],
    reserved_vertices: set[tuple[tuple[int, int], int]],
    reserved_edges: set[tuple[tuple[tuple[int, int], tuple[int, int]], int]],
    horizon: int,
) -> list[tuple[int, int]] | None:
    start_state = (start, 0)
    if (start, 0) in reserved_vertices:
        return None

    queue = deque([start_state])
    parent: dict[tuple[tuple[int, int], int], tuple[tuple[int, int], int] | None] = {start_state: None}

    while queue:
        current_cell, current_time = queue.popleft()
        if current_cell == goal:
            path: list[tuple[int, int]] = []
            state: tuple[tuple[int, int], int] | None = (current_cell, current_time)
            while state is not None:
                path.append(state[0])
                state = parent[state]
            return path[::-1]
        if current_time >= horizon:
            continue

        for nxt in _neighbors(grid, current_cell):
            next_time = current_time + 1
            next_state = (nxt, next_time)
            if next_state in parent:
                continue
            if next_state in reserved_vertices:
                continue
            if ((current_cell, nxt), next_time) in reserved_edges:
                continue
            if ((nxt, current_cell), next_time) in reserved_edges:
                continue
            parent[next_state] = (current_cell, current_time)
            queue.append(next_state)

    return None


def _reserve_path(
    path: list[tuple[int, int]],
    reserved_vertices: set[tuple[tuple[int, int], int]],
    reserved_edges: set[tuple[tuple[tuple[int, int], tuple[int, int]], int]],
    horizon: int,
) -> None:
    for t, cell in enumerate(path):
        reserved_vertices.add((cell, t))
        if t > 0:
            reserved_edges.add(((path[t - 1], cell), t))
    goal = path[-1]
    for t in range(len(path), horizon + 1):
        reserved_vertices.add((goal, t))


def plan_paths(grid, starts, goals):
    grid = tuple(str(row) for row in grid)
    starts = tuple(tuple(cell) for cell in starts)
    goals = tuple(tuple(cell) for cell in goals)

    if len(starts) != len(goals):
        raise ValueError("starts and goals must have the same length")

    order = sorted(
        range(len(starts)),
        key=lambda idx: _shortest_path_length(grid, starts[idx], goals[idx]),
        reverse=True,
    )
    horizon = max(40, len(grid) * len(grid[0]) * 2)

    reserved_vertices: set[tuple[tuple[int, int], int]] = set()
    reserved_edges: set[tuple[tuple[tuple[int, int], tuple[int, int]], int]] = set()
    paths: list[list[tuple[int, int]] | None] = [None] * len(starts)

    for robot_idx in order:
        path = _space_time_bfs(
            grid,
            starts[robot_idx],
            goals[robot_idx],
            reserved_vertices,
            reserved_edges,
            horizon,
        )
        if path is None:
            raise RuntimeError(f"failed to plan path for robot {robot_idx}")
        paths[robot_idx] = path
        _reserve_path(path, reserved_vertices, reserved_edges, horizon)

    return [path for path in paths if path is not None]


def solve(instance):
    return plan_paths(instance["grid"], instance["starts"], instance["goals"])


if __name__ == "__main__":
    instance = benchmark_problem.load_instance()
    paths = plan_paths(instance["grid"], instance["starts"], instance["goals"])
    print(benchmark_problem.total_cost(paths))

