# Fuel-Minimizing Ship Weather Routing Task

## Problem

You must route a ship from a fixed start cell to a fixed goal cell on a frozen coastal grid.
The route must avoid land and minimize fuel consumption under deterministic wind and current fields.

This is a weighted shortest-path problem on a grid graph.
The graph is fixed, but the edge weights are induced by the physics model.

## Background

Imagine a coastal navigation problem where a ship moves one grid cell at a time.
Some cells are land and cannot be entered.
The interesting part is that moving east, west, north, or south does not cost the same amount everywhere.

The fuel cost of a move depends on the local wind and current.
Following favorable current can reduce travel time and fuel, while fighting headwind or adverse current increases both.
That means the shortest geometric path is often not the cheapest route.

From a CS point of view, this is still a shortest-path problem.
The difference is that the edge weights are not uniform and are not purely geometric.
That is what makes the benchmark a good example of physics-aware routing.

## What Is Frozen

- The grid map.
- The start cell.
- The goal cell.
- The deterministic wind field.
- The deterministic current field.
- The fuel and time model used to score each move.
- The route validator.

## Input and Output

Your candidate file should define:

```python
def solve(instance):
    ...
```

`instance` is a dictionary with at least:

- `grid`
- `start`
- `goal`
- `current_field`
- `wind_field`
- `objective`

The function must return either:

- a list of `(x, y)` cells, or
- a dictionary with a `path` key

The path must:

- start at `instance["start"]`
- end at `instance["goal"]`
- move only between adjacent grid cells
- stay on water cells

## Expected Result

A good solution should return a feasible route with low fuel usage.
The evaluator also reports travel time and hop count, but fuel is the objective.

The reference solver in this scaffold uses exact Dijkstra search on the frozen grid with the fuel model as edge weights, so it can report the best fuel cost found for this instance.

## Scoring

This is a minimization task.
We normalize the score against the baseline and the exact reference fuel cost:

```text
normalized_score = 100 * clip((baseline_fuel - candidate_fuel) / (baseline_fuel - optimal_fuel), 0, 1)
```

Interpretation:

- `0` means the candidate is no better than the baseline
- `100` means the candidate matches the exact reference fuel cost
- invalid submissions receive `0`

We also report:

- `candidate_fuel`
- `baseline_fuel`
- `reference_fuel`
- `candidate_time_h`
- `baseline_time_h`
- `candidate_hops`
- `theoretical_optimum_fuel`

## Why This Is Hard

The simplest solution is to search for the shortest hop path and stop there.
That is usually valid, but it ignores wind and current.

The harder and more realistic version is weighted shortest path.
You need to reason about the actual cost of each move, not just the number of moves.
That is the central algorithmic lesson here.

## Failure Cases

The submission is invalid if:

- `solve` is missing
- the returned value cannot be parsed into a path
- the path leaves the map, enters land, or uses non-adjacent steps
- the evaluator cannot import or run the candidate file

<!-- AI_GENERATED -->
