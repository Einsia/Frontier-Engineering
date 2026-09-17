# Multi-Robot Prioritized Planning Task

## Problem

Plan collision-free paths for three robots on a frozen grid while minimizing total path cost.

This benchmark models small-fleet coordination in shared aisles. Good path sets reduce blocking and deadlocks without inflating overall travel cost.

This is small-scale multi-agent path finding: single-agent shortest paths are easy, but coordinating several paths without vertex or edge conflicts is the real challenge.

## What Is Frozen

- The occupancy grid, the three start-goal pairs, and the collision checker in `runtime/problem.py`.
- The rule that each robot path may move to an adjacent cell or wait in place, but all robots must avoid vertex and edge-swap collisions.
- The baseline prioritized planner and the individual-path lower bound reported for context.

## Submission Contract

Submit one Python file that defines:

```python
def plan_paths(grid, starts, goals):
    ...
```

Return a list of paths, one per robot. A dict with key `paths` is also accepted.

## Evaluation

1. Load the frozen grid, starts, and goals from `runtime/problem.py`.
2. Validate every robot path mechanically, including starts, goals, adjacency-or-wait moves, and obstacle checks.
3. Check joint execution for vertex collisions and edge-swap collisions across time.
4. Report total path cost, makespan, baseline total cost, and the lower-bound diagnostic.

## Metrics

- `combined_score`: `-candidate_total_cost`
- `valid`: `1.0` only if all robot paths are collision-free
- `candidate_total_cost`
- `baseline_total_cost`
- `candidate_makespan`
- `lower_bound_total_cost`

## Invalid Submissions

- `plan_paths(...)` is missing or crashes
- The returned value cannot be parsed into one path per robot
- Any robot path has the wrong start or goal, contains an illegal move, or enters an obstacle
- The joint path set contains a vertex collision or an edge-swap collision

<!-- AI_GENERATED -->
