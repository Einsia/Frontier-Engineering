from __future__ import annotations

from collections import deque
from heapq import heappop, heappush
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


def _distance_map(grid: tuple[str, ...], goal: tuple[int, int]) -> dict[tuple[int, int], int]:
    queue = deque([goal])
    distance = {goal: 0}
    while queue:
        current = queue.popleft()
        for nxt in _neighbors(grid, current):
            if nxt not in distance:
                distance[nxt] = distance[current] + 1
                queue.append(nxt)
    return distance


def _heuristic(state: tuple[tuple[int, int], ...], goals: tuple[tuple[int, int], ...], distance_maps: list[dict[tuple[int, int], int]]) -> int:
    total = 0
    for idx, pos in enumerate(state):
        if pos == goals[idx]:
            continue
        distance = distance_maps[idx].get(pos)
        if distance is None:
            return 10**9
        total += distance
    return total


def _reconstruct_states(parent: dict[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...] | None], goal_state: tuple[tuple[int, int], ...]) -> list[tuple[tuple[int, int], ...]]:
    sequence = []
    state: tuple[tuple[int, int], ...] | None = goal_state
    while state is not None:
        sequence.append(state)
        state = parent[state]
    return sequence[::-1]


def _next_states(current: tuple[tuple[int, int], ...], goals: tuple[tuple[int, int], ...], grid: tuple[str, ...]) -> list[tuple[tuple[int, int], ...]]:
    action_sets: list[list[tuple[int, int]]] = []
    for idx, pos in enumerate(current):
        if pos == goals[idx]:
            action_sets.append([pos])
        else:
            action_sets.append(_neighbors(grid, pos))

    candidates: list[tuple[tuple[int, int], ...]] = []

    def recurse(robot_idx: int, prefix: list[tuple[int, int]]) -> None:
        if robot_idx == len(current):
            nxt = tuple(prefix)
            if len(set(nxt)) != len(nxt):
                return
            for i in range(len(current)):
                for j in range(i + 1, len(current)):
                    if current[i] == nxt[j] and current[j] == nxt[i]:
                        return
            candidates.append(nxt)
            return

        for choice in action_sets[robot_idx]:
            recurse(robot_idx + 1, prefix + [choice])

    recurse(0, [])
    return candidates


def plan_paths(grid, starts, goals):
    grid = tuple(str(row) for row in grid)
    starts = tuple(tuple(cell) for cell in starts)
    goals = tuple(tuple(cell) for cell in goals)

    distance_maps = [_distance_map(grid, goal) for goal in goals]
    start_state = starts
    goal_state = goals

    open_heap: list[tuple[int, int, tuple[tuple[int, int], ...]]] = []
    heappush(open_heap, (_heuristic(start_state, goals, distance_maps), 0, start_state))
    best_g = {start_state: 0}
    parent: dict[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...] | None] = {start_state: None}

    while open_heap:
        _, g, current = heappop(open_heap)
        if g != best_g.get(current):
            continue
        if current == goal_state:
            joint_states = _reconstruct_states(parent, current)
            paths: list[list[tuple[int, int]]] = []
            for robot_idx, goal in enumerate(goals):
                path: list[tuple[int, int]] = []
                for state in joint_states:
                    path.append(state[robot_idx])
                    if state[robot_idx] == goal:
                        break
                paths.append(path)
            return paths

        step_cost = sum(1 for pos, goal in zip(current, goals) if pos != goal)
        for nxt in _next_states(current, goals, grid):
            tentative_g = g + step_cost
            if tentative_g >= best_g.get(nxt, 10**18):
                continue
            best_g[nxt] = tentative_g
            parent[nxt] = current
            f = tentative_g + _heuristic(nxt, goals, distance_maps)
            heappush(open_heap, (f, tentative_g, nxt))

    raise RuntimeError("exact joint-state search failed to find a solution")


def solve(instance):
    return plan_paths(instance["grid"], instance["starts"], instance["goals"])


EXACT_OPTIMUM_AVAILABLE = True


if __name__ == "__main__":
    instance = benchmark_problem.load_instance()
    paths = plan_paths(instance["grid"], instance["starts"], instance["goals"])
    print(benchmark_problem.total_cost(paths))

