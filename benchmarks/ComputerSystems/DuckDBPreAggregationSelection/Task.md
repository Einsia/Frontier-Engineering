# DuckDB Pre-Aggregation Selection Task

## Problem

Choose a whitelist subset of pre-aggregation tables for a frozen DuckDB reporting workload and minimize total runtime.

This benchmark models a very common warehouse decision: which summary tables are worth materializing for a recurring reporting workload. The wrong choice wastes storage and refresh time; the right choice reduces repeated scan and aggregation cost.

Algorithmically, it is a materialized-view selection problem over a fixed candidate set, scored by real query execution under exact-result checks.

## What Is Frozen

- The schema, local data generator, and reporting workload in `runtime/problem.py`.
- The whitelist of legal summary tables in `workload_manifest["candidate_preaggregations"]`.
- The correctness audit and the timing protocol used to compare setup plus repeated report execution.

## Submission Contract

Submit one Python file that defines:

```python
def select_preaggregations(workload_manifest):
    ...
```

Return a list of whitelist pre-aggregation names. A dict with key `preaggregations` is also accepted.

## Evaluation

1. Build the frozen DuckDB database and load the workload manifest.
2. Create the pre-aggregation tables you selected from the whitelist.
3. Run the fixed reporting queries and verify result equivalence.
4. Measure total candidate runtime and report the no-materialization baseline for context.

## Metrics

- `combined_score`: `-candidate_total_runtime_s`
- `valid`: `1.0` only if all selected names are legal and query results stay unchanged
- `candidate_total_runtime_s`
- `baseline_total_runtime_s`
- `candidate_setup_runtime_s`
- `candidate_workload_runtime_s`

## Invalid Submissions

- `select_preaggregations(...)` is missing or crashes
- The return value cannot be parsed into a list of names
- Any selected name is outside the whitelist
- Materialization or query execution fails, or results change

<!-- AI_GENERATED -->
