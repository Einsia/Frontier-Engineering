# EOQ with Minimum Order Quantity Task

## Problem

Choose an order quantity for frozen deterministic EOQ cases with a hard minimum order quantity and minimize average annual cost.

Supplier MOQs are a routine constraint in procurement. They change working-capital usage and warehouse occupancy, and they often push the feasible optimum onto a boundary that a naive EOQ formula misses.

This is a small constrained optimization problem over a frozen analytic cost model. The important part is boundary-aware decision logic, not systems integration.

## What Is Frozen

- The deterministic EOQ case table and annual-cost model in `runtime/problem.py`.
- The demand, setup cost, holding cost, and MOQ parameters for every frozen case.
- The evaluator loop that averages candidate cost across all cases.

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
4. Check the MOQ constraint, compute annual cost, and average cost across all cases.

## Metrics

- `combined_score`: `-avg_cost`
- `valid`: `1.0` only if every case is feasible and every output is finite
- `avg_cost`
- `avg_cost_ratio`: average `baseline_cost / candidate_cost` for diagnostics

## Invalid Submissions

- `solve(...)` is missing or crashes
- The returned value cannot be parsed into an order quantity
- Any order quantity violates the MOQ or is non-finite
- Any case evaluation produces a non-finite metric

<!-- AI_GENERATED -->
