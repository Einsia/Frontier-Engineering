from __future__ import annotations

try:
    from benchmarks.Robotics.GridPathPlanningWithObstacles.runtime.problem import baseline_plan
except ModuleNotFoundError:
    from runtime.problem import baseline_plan


def plan_path(grid, start, goal):
    return baseline_plan()
