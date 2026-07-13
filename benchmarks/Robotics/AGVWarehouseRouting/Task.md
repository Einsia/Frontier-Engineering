# AGV Warehouse Routing

## Background

Warehouses often run fleets of automated guided vehicles to pick parts, bins, or
parcels. Even for one vehicle, the best visit order depends on aisle topology,
blocked cells, turn cost, congestion zones, and required return location. Better
ordering reduces cycle time and battery usage without changing warehouse layout.

## Objective

Given a fixed warehouse instance, return the order in which the AGV should visit
all required pick locations before ending at the outbound station. The evaluator
uses a deterministic shortest-path model between visits and sums travel,
congestion, and turn costs.

## Candidate API

The evaluator imports `plan_order(instance)` from `scripts/init.py`.

`instance` contains:

- `instance_id`
- `rows`, `cols`
- `grid`: list of strings, where `#` marks blocked cells
- `start`: `[row, col]`
- `goal`: `[row, col]`
- `picks`: list of `{id, row, col, priority}`
- `traffic`: list of `{row, col, extra_cost}`
- `turn_penalty`

Return a list of pick ids. Every id must appear exactly once.

## Constraints

- Do not import external packages.
- Do not read or write files.
- Keep the public `plan_order(instance)` interface.
- Keep all editable logic inside the EVOLVE block.
- The policy must be deterministic for the same input instance.

## Scoring

The evaluator computes the least-cost grid path from start through the returned
pick sequence and then to goal. Cell traversal cost includes base travel cost,
traffic surcharge, and heading-change penalties.

`combined_score = -mean(route_cost across instances)`, so higher is better.
Invalid permutations or unreachable routes receive an invalid score.
