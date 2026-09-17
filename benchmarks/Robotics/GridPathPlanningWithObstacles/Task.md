# Grid Path Planning with Obstacles Task

## Problem

Plan a collision-free path on a frozen 2D occupancy grid with static obstacles and keep path cost low.

This benchmark mirrors warehouse-like navigation with blocked aisles and shelves. A shorter valid path reduces cycle time, battery use, and congestion.

It is a graph-search problem on a frozen grid map. The evaluator already defines the graph, legality checks, and cost function; you only supply the path.

## What Is Frozen

- The occupancy grid, start cell, goal cell, and path validator in `runtime/problem.py`.
- The movement rule: each step must stay in free space and move between adjacent grid cells.
- The baseline path and the shortest-path reference cost reported for context.

## Submission Contract

Submit one Python file that defines:

```python
def plan_path(grid, start, goal):
    ...
```

Return a path as a sequence of `(x, y)` cells. A dict with key `path` is also accepted.

## Evaluation

1. Load the frozen grid, start, and goal from `runtime/problem.py`.
2. Validate the returned path against the start/end cells, adjacency rule, and obstacle mask.
3. Compute candidate path cost as path length minus one.
4. Report candidate cost together with baseline and shortest-path reference costs.

## Metrics

- `combined_score`: `-candidate_cost`
- `valid`: `1.0` only if the path is finite and collision-free
- `candidate_cost`
- `baseline_cost`
- `reference_cost`

## Invalid Submissions

- `plan_path(...)` is missing or crashes
- The returned value cannot be parsed into a path
- The path has the wrong start or goal, contains a non-adjacent move, or enters an obstacle
- Any reported metric becomes non-finite

<!-- AI_GENERATED -->
