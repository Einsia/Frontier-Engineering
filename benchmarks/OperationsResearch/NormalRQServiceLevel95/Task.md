# Normal (r,Q) with 95% Service-Level Constraint Task

## Problem

Choose `(r, Q)` policies for frozen Normal-demand inventory cases with a hard 95% service-level target and minimize average cost.

This benchmark captures policy tuning near a service-level boundary. Small changes in reorder point can materially change stockout risk and working capital when the target is fixed around 95%.

Algorithmically, it is a small constrained discrete optimization problem over a frozen probabilistic model.

## What Is Frozen

- The Normal-demand case table, service-level target, and cost model in `runtime/problem.py`.
- The candidate-pair audit used to check service-level feasibility.
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
- Any case misses the 95% service-level target or returns non-finite values
- Any case evaluation produces a non-finite metric

<!-- AI_GENERATED -->
