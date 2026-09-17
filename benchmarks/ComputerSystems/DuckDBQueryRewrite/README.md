# DuckDB Query Rewrite

Rewrite one frozen analytical DuckDB query so that results stay identical while runtime decreases.

## Why This Benchmark Matters

This benchmark stands in for real SQL performance tuning, where engineers often cannot change upstream product logic but can still rewrite a slow analytical query. Runtime matters, but only after semantic equivalence is preserved exactly.

From a CS point of view, this is a semantics-preserving program transformation problem where the “program” happens to be SQL.

## What You Edit

- Target file: `scripts/init.py`
- Entry point: `rewrite_query(sql, workload_manifest)`

## Source of Truth

- `Task.md`: full task contract and scoring rules
- `Task_zh-CN.md`: Chinese translation of the task contract
- `runtime/problem.py`: frozen instance, validator, and metrics helpers
- `baseline/solution.py`: reference baseline
- `verification/evaluator.py`: local evaluator entry point
- `references/source_manifest.md`: provenance and lineage notes

## Environment

From repository root:

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/ComputerSystems/DuckDBQueryRewrite/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/ComputerSystems/DuckDBQueryRewrite/verification/evaluator.py \
  benchmarks/ComputerSystems/DuckDBQueryRewrite/scripts/init.py \
  --metrics-out /tmp/DuckDBQueryRewrite_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/DuckDBQueryRewrite \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
