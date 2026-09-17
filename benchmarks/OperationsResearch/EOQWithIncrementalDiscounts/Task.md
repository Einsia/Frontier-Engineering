# EOQ with Incremental Discounts Task

## Problem

Choose an order quantity for frozen EOQ cases with incremental discounts and minimize average annual cost.

Incremental discount contracts are common in industrial purchasing: only the units beyond each breakpoint get the lower price. Correctly reasoning about the cumulative tiered purchase cost matters just as much as choosing a good order size.

From a CS angle, this is again a small frozen search problem, but the cost accounting is cumulative across tiers rather than a simple breakpoint lookup.

## What Is Frozen

- The deterministic EOQ case table and incremental-discount cost model in `runtime/problem.py`.
- The tier boundaries and price schedule for every frozen case.
- The evaluator loop that averages annual cost across the entire case set.

## Submission Contract

Submit one Python file that defines:

```python
def solve(instance):
    ...
```

Return either a raw numeric order quantity or a dict with key `order_quantity`.

## Evaluation

1. Load the frozen case set from `runtime/problem.py`.
2. Run the reference baseline on every case for diagnostics.
3. Run your `solve(instance)` on every case and parse the returned order quantity.
4. Convert that quantity into feasibility and annual cost under the incremental schedule, then average cost across cases.

## Metrics

- `combined_score`: `-avg_cost`
- `valid`: `1.0` only if every case is feasible and every output is finite
- `avg_cost`
- `avg_cost_ratio`: average `baseline_cost / candidate_cost` for diagnostics

## Invalid Submissions

- `solve(...)` is missing or crashes
- The returned value cannot be parsed into an order quantity
- Any order quantity is infeasible or non-finite
- Any case evaluation produces a non-finite metric

<!-- AI_GENERATED -->
