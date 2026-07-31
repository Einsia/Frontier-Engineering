# Task

You are given a batch of analytics queries and a fixed total differential-privacy budget. Allocate a nonnegative epsilon value to every query.

Each query contains:

- `id`: query identifier.
- `sensitivity`: sensitivity used in the deterministic error model.
- `business_value`: value weight for the query.
- `population_coverage`: covered population fraction or weight.
- `epsilon_min`: minimum allowed privacy budget.
- `epsilon_max`: maximum allowed privacy budget.
- `max_error`: maximum allowed estimation error.
- `group`: population group label used for fairness checks.

The estimation error for a query is `sensitivity / epsilon`. Allocations must satisfy every per-query bound, every per-query maximum error, the total budget limit, and the group fairness ratio over average group errors.

## Required Output

Return a dictionary with one key:

```python
{
  "allocations": {
    "query_id": epsilon
  }
}
```

The allocation map must contain exactly the required query IDs and finite numeric epsilon values.

## Objective

After feasibility checks pass, the verifier computes a positive raw utility. Larger values are better. The metric rewards useful analytics budget and penalizes estimation error. Normalization is handled by the benchmark framework.

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## Input Schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "queries",
    "epsilon_total",
    "fairness"
  ],
  "properties": {
    "queries": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "sensitivity",
          "business_value",
          "population_coverage",
          "epsilon_min",
          "epsilon_max",
          "max_error",
          "group"
        ],
        "properties": {
          "id": {
            "type": "string"
          },
          "sensitivity": {
            "type": "number",
            "minimum": 0
          },
          "business_value": {
            "type": "number",
            "minimum": 0
          },
          "population_coverage": {
            "type": "number",
            "minimum": 0
          },
          "epsilon_min": {
            "type": "number",
            "minimum": 0
          },
          "epsilon_max": {
            "type": "number",
            "minimum": 0
          },
          "max_error": {
            "type": "number",
            "minimum": 0
          },
          "group": {
            "type": "string"
          }
        }
      }
    },
    "epsilon_total": {
      "type": "number",
      "minimum": 0
    },
    "fairness": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "max_group_error_ratio"
      ],
      "properties": {
        "max_group_error_ratio": {
          "type": "number",
          "minimum": 1
        }
      }
    }
  }
}
```

## Output Schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "allocations"
  ],
  "properties": {
    "allocations": {
      "type": "object",
      "additionalProperties": true
    }
  }
}
```

## Constraints and Objective

The output must satisfy every hard constraint described above. The frozen verifier independently
checks feasibility and recomputes `Verifier-owned positive raw utility: 1.0 plus the sum over queries of business_value * population_coverage * log1p(epsilon) minus deterministic error penalties, evaluated only after all feasibility checks pass.`. The objective is to maximize
that strictly positive raw metric. Valid cases use `log2` baseline improvement and are aggregated
with the mean; invalid solutions receive `-1e18`.

The problem setting is `offline_batch`. Objective rationale: The primary objective is appropriate because privacy budget is a scarce resource and the economically relevant decision is the feasible allocation that preserves the most weighted analytics utility while controlling estimation error. Accuracy and fairness are hard feasibility requirements so the objective cannot trade them away beyond accepted policy limits.
Literature alignment: The supplied brief aligns with differential-privacy budget-allocation work at the level of allocating limited privacy loss across multiple analytics queries and recomputing privacy loss and error from first principles. This benchmark differs by making the task an offline batch portfolio optimization problem with explicit business values, population coverage, fairness constraints, and a structured candidate output rather than an interactive privacy accountant or a single-query mechanism design task.
<!-- BENCHGEN-PUBLIC-CONTRACT-END -->
