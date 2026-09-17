# EOQ with All-Units Discounts Task

## Problem

Choose an order quantity for frozen EOQ cases with all-units discounts and minimize average annual cost.

All-units discounts appear in packaging, chemicals, and contract manufacturing. Crossing a breakpoint changes the unit price of every unit in the order, so choosing the wrong region can dominate annual spend.

This is a frozen piecewise optimization problem with regime switches. The output is still a single scalar `Q`, but the objective changes discontinuously when the chosen price region changes.

## What Is Frozen

- The deterministic EOQ case table and cost model in `runtime/problem.py`.
- The price-break schedule, demand, holding-cost, and order-cost parameters for every case.
- The evaluator loop that averages cost across all frozen cases.

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
4. Convert that quantity into feasibility and annual cost, then average cost across all cases.

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
