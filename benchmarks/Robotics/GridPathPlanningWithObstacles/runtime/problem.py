from __future__ import annotations

from heapq import heappop, heappush
import random
from typing import Any

GRID = (
    '####################',
    '#S........####.....#',
    '#..###..#.#.#..##..#',
    '#...#....##.......##',
    '#...#.#.......##..##',
    '#.#.#......#...###.#',
    '##......#.......#..#',
    '#................#.#',
    '#....##.#.......#..#',
    '#.........#....#.#.#',
    '##..#.#.#..##...#..#',
    '#.......##.........#',
    '#..##.......#...##G#',
    '####################',
)
BASELINE_KIND = "greedy"
BASELINE_SEED = 0
BASELINE_ITERATIONS = 0


def _parse_grid() -> tuple[tuple[str, ...], tuple[int, int], tuple[int, int]]:
    start = None
    goal = None
    rows = []
    for y, row in enumerate(GRID):
        new_row = []
        for x, cell in enumerate(row):
            if cell == 'S':
                start = (x, y)
                new_row.append('.')
            elif cell == 'G':
                goal = (x, y)
                new_row.append('.')
            else:
                new_row.append(cell)
        rows.append(''.join(new_row))
    if start is None or goal is None:
        raise ValueError('grid must contain both S and G')
    return tuple(rows), start, goal


FREE_GRID, START, GOAL = _parse_grid()


def load_instance() -> dict[str, Any]:
    return {'grid': FREE_GRID, 'start': START, 'goal': GOAL}


def _to_cell(value: Any) -> tuple[int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError('cell must be a length-2 sequence')
    return int(round(float(value[0]))), int(round(float(value[1])))


def _extract_path(value: Any) -> list[tuple[int, int]]:
    if isinstance(value, dict):
        if 'path' not in value:
            raise ValueError('missing path')
        value = value['path']
    path = [_to_cell(cell) for cell in value]
    if not path:
        raise ValueError('path is empty')
    return path


def is_free(cell: tuple[int, int]) -> bool:
    x, y = cell
    return 0 <= y < len(FREE_GRID) and 0 <= x < len(FREE_GRID[0]) and FREE_GRID[y][x] != '#'


def neighbors(cell: tuple[int, int]) -> list[tuple[int, int]]:
    x, y = cell
    result = []
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        candidate = (nx, ny)
        if is_free(candidate):
            result.append(candidate)
    return result


def _retrace(parent, node):
    path = []
    current = node
    while current is not None:
        path.append(current)
        current = parent[current]
    return path[::-1]


def greedy_best_first_path(grid, start, goal):
    frontier = [(abs(start[0] - goal[0]) + abs(start[1] - goal[1]), start)]
    parent = {start: None}
    visited = set()
    while frontier:
        _, current = heappop(frontier)
        if current in visited:
            continue
        visited.add(current)
        if current == goal:
            return _retrace(parent, current)
        for nxt in neighbors(current):
            if nxt in visited or nxt in parent:
                continue
            parent[nxt] = current
            h = abs(nxt[0] - goal[0]) + abs(nxt[1] - goal[1])
            heappush(frontier, (h, nxt))
    return None


def rrt_path(grid, start, goal, seed, iterations, goal_probability=0.2):
    rng = random.Random(seed)
    free_cells = [(x, y) for y, row in enumerate(grid) for x, cell in enumerate(row) if cell != '#']
    parent = {start: None}
    nodes = [start]
    for _ in range(iterations):
        target = goal if rng.random() < goal_probability else rng.choice(free_cells)
        nearest = min(nodes, key=lambda cell: abs(cell[0] - target[0]) + abs(cell[1] - target[1]))
        candidates = neighbors(nearest)
        rng.shuffle(candidates)
        candidates.sort(key=lambda cell: abs(cell[0] - target[0]) + abs(cell[1] - target[1]))
        for nxt in candidates:
            if nxt in parent:
                continue
            parent[nxt] = nearest
            nodes.append(nxt)
            if nxt == goal:
                return _retrace(parent, nxt)
            break
    return None


def baseline_plan():
    if BASELINE_KIND == 'greedy':
        path = greedy_best_first_path(FREE_GRID, START, GOAL)
    elif BASELINE_KIND == 'rrt':
        path = rrt_path(FREE_GRID, START, GOAL, BASELINE_SEED, BASELINE_ITERATIONS)
    else:
        raise ValueError(f'unsupported baseline kind: {BASELINE_KIND}')
    if path is None:
        raise RuntimeError('baseline planner failed to find a path')
    return path


def validate_path(path_value: Any):
    path = _extract_path(path_value)
    if path[0] != START:
        raise ValueError('path does not start at START')
    if path[-1] != GOAL:
        raise ValueError('path does not end at GOAL')
    for cell in path:
        if not is_free(cell):
            raise ValueError('path enters an obstacle or leaves the grid')
    for previous, current in zip(path, path[1:]):
        dx = abs(previous[0] - current[0])
        dy = abs(previous[1] - current[1])
        if dx + dy not in {0, 1}:
            raise ValueError('path contains a non-adjacent move')
    return path


def path_cost(path_value: Any) -> int:
    return len(validate_path(path_value)) - 1


REFERENCE_COST = 28
