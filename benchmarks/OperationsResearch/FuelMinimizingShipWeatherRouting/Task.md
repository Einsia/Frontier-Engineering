# Fuel-Minimizing Ship Weather Routing Task

## Problem

Route a ship across a frozen coastal grid while minimizing fuel consumption under deterministic wind and current fields.

This benchmark stands in for weather-aware voyage planning. The shortest geometric route is rarely the cheapest once headwind, crosswind, and current penalties are folded into the fuel model.

It is a constrained routing problem on a fixed grid graph whose edge costs are induced by environmental fields.

## What Is Frozen

- The coastal land mask, water cells, deterministic wind field, and deterministic current field in `runtime/problem.py`.
- The start cell, goal cell, and the rule that paths move only between adjacent navigable cells.
- The fuel and travel-time model used to score the returned route.

## Submission Contract

Submit one Python file that defines:

```python
def solve(instance):
    ...
```

Return either a list of grid cells or a dict with key `path`. The path must start at `instance["start"]`, end at `instance["goal"]`, move only between adjacent cells, and stay on navigable water cells.

## Evaluation

1. Load the frozen routing instance from `runtime/problem.py`.
2. Validate the returned path against the start/end cells, adjacency rule, and land mask.
3. Compute total fuel and travel time along the route.
4. Report candidate fuel together with baseline and reference metrics for context.

## Metrics

- `combined_score`: `-candidate_fuel`
- `valid`: `1.0` only if the route is feasible
- `candidate_fuel`
- `baseline_fuel`
- `reference_fuel`
- `candidate_time_h`
- `baseline_time_h`

## Invalid Submissions

- `solve(...)` is missing or crashes
- The returned value cannot be parsed into a path
- The path has the wrong start or goal, contains a non-adjacent move, or touches land
- Any reported metric becomes non-finite

<!-- AI_GENERATED -->
