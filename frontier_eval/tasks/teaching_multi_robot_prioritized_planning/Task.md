# Multi-Robot Prioritized Planning Task

## Problem

You must plan collision-free paths for three robots on a frozen occupancy grid.
The evaluator checks whether the paths are individually valid, whether the robots collide with each other, and how expensive the joint plan is.

This is a prioritized planning problem.
The robots are planned one at a time in a chosen priority order.
When a robot is planned, the already planned robots become moving obstacles in space-time.

## Background

Single-robot shortest path planning is not enough once multiple robots share the same aisles.
Even if each robot has a good path by itself, two robots can still collide at the same cell at the same time, or swap cells across the same edge in opposite directions.

That is why multi-robot planning is often solved by decomposition:
pick an ordering of robots, plan the first robot, reserve its path, then plan the next robot against those reservations.

This benchmark keeps the instance tiny on purpose.
There are only three robots, which makes the teaching point clear:
the difficult part is not path search itself, but the interaction between path search and coordination.

## What Is Frozen

- The occupancy grid.
- The three start-goal pairs.
- The collision rules.
- The fact that each robot may wait in place or move to an adjacent free cell.
- The reference instance has exactly three robots, which makes exact search over this tiny frozen case feasible.

## Input and Output

Your candidate file should define:

```python
def plan_paths(grid, starts, goals):
    ...
```

Inputs:

- `grid`: a tuple of strings, where `#` is an obstacle and `.` is free space
- `starts`: a tuple of `(x, y)` start cells, one per robot
- `goals`: a tuple of `(x, y)` goal cells, one per robot

Output:

- a list of paths, one path per robot

A dictionary with a `paths` field is also accepted by the evaluator.

Each path is a sequence of grid cells.
The first cell must equal the robot start.
The last cell must equal the robot goal.
Each step must either stay in place or move to one of the four neighboring cells.

The evaluator will reject paths that leave the grid, enter obstacles, or violate collision rules.

## Expected Result

A good solution should produce a feasible set of paths and keep the total path length small.
The evaluator measures:

- `candidate_total_cost = sum(len(path) - 1 for path in paths)`
- `candidate_makespan = max(len(path) - 1 for path in paths)`

The reference implementation in this scaffold performs exact search on the tiny frozen 3-robot instance, so it can report the best total cost achievable by this teaching problem.

## Scoring

This is a minimization task.
We use the exact best total cost found by the reference solver as the theoretical upper bound for scoring.

```text
normalized_score = 100 * clip((baseline_total_cost - candidate_total_cost) / (baseline_total_cost - optimal_total_cost), 0, 1)
```

Interpretation:

- `0` means the candidate is no better than the baseline
- `100` means the candidate matches the best total cost found by the exact reference search
- invalid submissions receive `0`

We also report:

- `baseline_total_cost`
- `reference_total_cost`
- `lower_bound_total_cost`
- `candidate_makespan`
- `theoretical_optimum_total_cost`

## Why This Is Hard

The obvious idea is to plan each robot independently with shortest paths.
That fails as soon as two robots want to use the same corridor at the same time.

The next step is prioritized planning, but the priority order matters.
The first robot gets the most freedom, while later robots inherit all the reservations.
Choosing a bad order can make the instance look infeasible or force extra detours.

That is the optimization lesson here:
you are not only solving path planning, you are also choosing a coordination policy.

## Failure Cases

The submission is invalid if:

- `plan_paths` is missing
- the returned value is not a list of paths
- any path is malformed or non-adjacent
- any path enters an obstacle
- a vertex collision or edge-swap collision occurs
- the evaluator cannot import or run the candidate file

<!-- AI_GENERATED -->
