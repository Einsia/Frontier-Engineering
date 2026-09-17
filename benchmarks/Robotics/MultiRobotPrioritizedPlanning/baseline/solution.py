from __future__ import annotations

try:
    from benchmarks.Robotics.MultiRobotPrioritizedPlanning.runtime.problem import baseline_plan_paths
except ModuleNotFoundError:
    from runtime.problem import baseline_plan_paths


def plan_paths(grid, starts, goals):
    return baseline_plan_paths()
