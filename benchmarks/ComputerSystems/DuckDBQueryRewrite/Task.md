# DuckDB Query Rewrite Task

## Problem

Rewrite one frozen analytical DuckDB query so that results stay identical while runtime decreases.

This benchmark stands in for real SQL performance tuning, where engineers often cannot change upstream product logic but can still rewrite a slow analytical query. Runtime matters, but only after semantic equivalence is preserved exactly.

From a CS point of view, this is a semantics-preserving program transformation problem where the “program” happens to be SQL.

## What Is Frozen

- The schema, local data generator, original SQL, and workload manifest in `runtime/problem.py`.
- The exact-result equivalence check used by the evaluator.
- The repeated timing protocol for the candidate and baseline queries.

## Submission Contract

Submit one Python file that defines:

```python
def rewrite_query(sql, workload_manifest):
    ...
```

Return a rewritten SQL string. A dict with key `sql` is also accepted.

## Evaluation

1. Build the frozen DuckDB database and execute the original SQL to obtain the reference result.
2. Execute your rewritten SQL and check exact result equivalence.
3. If the results match, time repeated runs of the candidate query.
4. Report candidate runtime together with the original-query baseline for context.

## Metrics

- `combined_score`: `-candidate_runtime_s`
- `valid`: `1.0` only if the rewritten query preserves results exactly
- `candidate_runtime_s`
- `baseline_runtime_s`
- `row_count`

## Invalid Submissions

- `rewrite_query(...)` is missing or crashes
- The return value is not a SQL string or a dict with `sql`
- The rewritten query fails to execute
- The rewritten query changes the result set

<!-- AI_GENERATED -->
