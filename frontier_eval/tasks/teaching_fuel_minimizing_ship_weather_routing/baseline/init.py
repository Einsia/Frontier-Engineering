from __future__ import annotations

from collections import deque
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
    from benchmarks.OperationsResearch.FuelMinimizingShipWeatherRouting.runtime.problem import load_instance, route_metrics
except ModuleNotFoundError:
    from runtime.problem import load_instance, route_metrics


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


def solve(instance):
    grid = instance["grid"]
    start = instance["start"]
    goal = instance["goal"]

    queue = deque([start])
    parent = {start: None}
    while queue:
        current = queue.popleft()
        if current == goal:
            return _retrace(parent, current)
        for nxt in _neighbors(grid, current):
            if nxt not in parent:
                parent[nxt] = current
                queue.append(nxt)
    raise RuntimeError("baseline route not found")


if __name__ == "__main__":
    instance = load_instance()
    path = solve(instance)
    print(route_metrics(path)["fuel"])
