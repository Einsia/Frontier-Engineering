# DuckDB Pre-Aggregation Selection

Choose a whitelist subset of pre-aggregation tables for a frozen DuckDB reporting workload and minimize total runtime.

## Why This Benchmark Matters

This benchmark models a very common warehouse decision: which summary tables are worth materializing for a recurring reporting workload. The wrong choice wastes storage and refresh time; the right choice reduces repeated scan and aggregation cost.

Algorithmically, it is a materialized-view selection problem over a fixed candidate set, scored by real query execution under exact-result checks.

## What You Edit

- Target file: `scripts/init.py`
- Entry point: `select_preaggregations(workload_manifest)`

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
pip install -r benchmarks/ComputerSystems/DuckDBPreAggregationSelection/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/ComputerSystems/DuckDBPreAggregationSelection/verification/evaluator.py \
  benchmarks/ComputerSystems/DuckDBPreAggregationSelection/scripts/init.py \
  --metrics-out /tmp/DuckDBPreAggregationSelection_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/DuckDBPreAggregationSelection \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
