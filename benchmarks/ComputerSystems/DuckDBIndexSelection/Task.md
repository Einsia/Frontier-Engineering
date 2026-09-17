# DuckDB Index Selection Task

## Problem

Choose a whitelist subset of DuckDB indexes for a frozen analytical lookup workload and minimize total runtime.

This benchmark captures physical-design tuning on top of a stable DuckDB workload. Extra indexes can speed repeated queries, but they also add build and maintenance cost, so the goal is to choose the right subset rather than simply choosing more.

Viewed computationally, this is a subset-selection problem over a fixed candidate set, with real execution time rather than a proxy metric deciding the score.

## What Is Frozen

- The schema, local data generator, and workload manifest in `runtime/problem.py`.
- The whitelist of legal index names in `workload_manifest["candidate_indexes"]`.
- The timing protocol: index build plus four repeated workload executions.

## Submission Contract

Submit one Python file that defines:

```python
def select_indexes(workload_manifest):
    ...
```

Return a list of whitelist index names. A dict with key `indexes` is also accepted.

## Evaluation

1. Build the frozen DuckDB database and load the manifest.
2. Create the indexes you selected from the whitelist.
3. Run the fixed lookup workload four times.
4. Measure total candidate runtime and report no-index baseline numbers for context.

## Metrics

- `combined_score`: `-candidate_total_runtime_s`
- `valid`: `1.0` only if every selected index name is legal and execution succeeds
- `candidate_total_runtime_s`
- `baseline_total_runtime_s`
- `candidate_setup_runtime_s`
- `candidate_workload_runtime_s`

## Invalid Submissions

- `select_indexes(...)` is missing or crashes
- The return value cannot be parsed into a list of names
- Any selected name is outside the whitelist
- Index creation or workload execution fails

<!-- AI_GENERATED -->
