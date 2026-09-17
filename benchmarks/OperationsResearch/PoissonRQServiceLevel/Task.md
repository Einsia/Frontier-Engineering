# Poisson (r,Q) with Service-Level Constraint Task

## Problem

Choose `(r, Q)` policies for frozen Poisson-demand inventory cases with a hard service-level target and minimize average cost.

This benchmark models replenishment for spare parts and MRO inventory, where demand arrives as discrete events and service commitments still matter. Good policies cut stockouts without overspending on safety stock.

It is a small stochastic-policy tuning problem: the evaluator freezes the demand model and cost accounting, and your code only chooses the `(r, Q)` pair.

## What Is Frozen

- The Poisson-demand case table, service-level target, and cost model in `runtime/problem.py`.
- The feasibility audit used to check whether a returned `(r, Q)` pair meets the target.
- The evaluator loop that averages candidate cost across all frozen cases.

## Submission Contract

Submit one Python file that defines:

```python
def solve(instance):
    ...
```

Return either a 2-tuple `(reorder_point, order_quantity)` or a dict with keys `reorder_point` and `order_quantity`.

## Evaluation

1. Load the frozen case set from `runtime/problem.py`.
2. Run the reference baseline on every case for diagnostics.
3. Run your `solve(instance)` on every case and parse the returned `(r, Q)` pair.
4. Check the hard service-level constraint, compute annual cost, and average cost across all cases.

## Metrics

- `combined_score`: `-avg_cost`
- `valid`: `1.0` only if every case is feasible and every output is finite
- `avg_cost`
- `avg_cost_ratio`: average `baseline_cost / candidate_cost` for diagnostics

## Invalid Submissions

- `solve(...)` is missing or crashes
- The returned value cannot be parsed into an `(r, Q)` pair
- Any case misses the service-level target or returns non-finite values
- Any case evaluation produces a non-finite metric

<!-- AI_GENERATED -->
