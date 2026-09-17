# Dynamic-Current Minimum-Time Routing Task

## Problem

Route a ship across a frozen coastal grid while minimizing travel time under deterministic current and depth constraints.

This benchmark stands in for channel navigation and port-access planning. A fast route improves schedule reliability, but the shortest geometric route can be illegal or slow once current assistance and draft limits matter.

Algorithmically, it is a constrained shortest-path problem on a fixed grid graph with physics-induced edge costs.

## What Is Frozen

- The land mask, water cells, deterministic current field, and depth field in `runtime/problem.py`.
- The start cell, goal cell, minimum draft requirement, and four-neighbor movement rule.
- The travel-time computation and the reference metrics reported for baseline and Dijkstra-style routes.

## Submission Contract

Submit one Python file that defines:

```python
def solve(instance):
    ...
```

Return either a list of grid cells or a dict with key `path`. The path must start at `instance["start"]`, end at `instance["goal"]`, move only between adjacent cells, and stay on water cells with depth at least `instance["min_depth"]`.

## Evaluation

1. Load the frozen routing instance from `runtime/problem.py`.
2. Validate the returned path against the start/end cells, adjacency rule, land mask, and minimum-depth constraint.
3. Compute total travel time and hop count along the path.
4. Report candidate time together with baseline and reference metrics for context.

## Metrics

- `combined_score`: `-candidate_time_h`
- `valid`: `1.0` only if the route is feasible
- `candidate_time_h`
- `baseline_time_h`
- `reference_time_h`
- `candidate_hops`
- `baseline_hops`

## Invalid Submissions

- `solve(...)` is missing or crashes
- The returned value cannot be parsed into a path
- The path has the wrong start or goal, contains a non-adjacent move, or enters land/shallow water
- Any reported metric becomes non-finite

<!-- AI_GENERATED -->
