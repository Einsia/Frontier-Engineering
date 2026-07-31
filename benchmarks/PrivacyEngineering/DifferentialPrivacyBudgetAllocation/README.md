# Differential Privacy Budget Allocation for Business Analytics

Allocate a fixed differential-privacy budget across a batch of analytics queries. Each query has a sensitivity, business value, population coverage, minimum and maximum allowable epsilon, an error limit, and a population group. A solution must return one epsilon allocation per query.

The verifier checks hard constraints first: exact query coverage, finite numeric allocations, per-query bounds, total budget, maximum estimation error, and bounded group-level average error disparity. Feasible solutions are scored by a positive raw utility metric owned by the verifier.

## Candidate Interface

Implement `solve(instance)` in `scripts/init.py`.

Input fields:

- `queries`: list of query objects.
- `epsilon_total`: total privacy budget.
- `fairness.max_group_error_ratio`: maximum allowed ratio between the largest and smallest group average error.

Return:

```python
{"allocations": {query_id: epsilon, ...}}
```

The output must include exactly the query identifiers in the instance.

## Scoring

For feasible solutions, the raw metric is strictly positive and larger is better. It combines weighted analytics value with deterministic estimation-error penalties. Invalid or infeasible outputs receive the framework invalid score.

Framework scoring uses `log2_baseline_ratio` normalization outside the verifier.

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## Evaluation Contract

The verifier recomputes `Verifier-owned positive raw utility: 1.0 plus the sum over queries of business_value * population_coverage * log1p(epsilon) minus deterministic error penalties, evaluated only after all feasibility checks pass.` and candidates must maximize it.
Each valid case is scored by `log2` improvement over the baseline and the final score is the
mean across cases. Invalid solutions receive `-1e18`.

## Evaluation Design

Setting: `offline_batch`. Arrival model: All analytics-query portfolios are generated deterministically from fixed seeds before solving. A candidate receives a complete static instance containing query sensitivities, business values, population coverage, group memberships, bounds, fairness thresholds, accuracy requirements, and total budget, then returns one structured allocation for that instance.

Objective rationale: The primary objective is appropriate because privacy budget is a scarce resource and the economically relevant decision is the feasible allocation that preserves the most weighted analytics utility while controlling estimation error. Accuracy and fairness are hard feasibility requirements so the objective cannot trade them away beyond accepted policy limits.

Literature alignment: The supplied brief aligns with differential-privacy budget-allocation work at the level of allocating limited privacy loss across multiple analytics queries and recomputing privacy loss and error from first principles. This benchmark differs by making the task an offline batch portfolio optimization problem with explicit business values, population coverage, fairness constraints, and a structured candidate output rather than an interactive privacy accountant or a single-query mechanism design task.

Local execution is only for reviewed code:

```bash
python verification/evaluator.py scripts/init.py --local
```

Publish evaluation requires Docker and the pinned runtime image:

```bash
docker pull python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
python verification/evaluator.py scripts/init.py
```
<!-- BENCHGEN-PUBLIC-CONTRACT-END -->
