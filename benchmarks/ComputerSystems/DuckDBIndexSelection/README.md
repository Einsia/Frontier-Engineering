# DuckDB Index Selection

Choose a whitelist subset of DuckDB indexes for a frozen analytical lookup workload and minimize total runtime.

## Why This Benchmark Matters

This benchmark captures physical-design tuning on top of a stable DuckDB workload. Extra indexes can speed repeated queries, but they also add build and maintenance cost, so the goal is to choose the right subset rather than simply choosing more.

Viewed computationally, this is a subset-selection problem over a fixed candidate set, with real execution time rather than a proxy metric deciding the score.

## What You Edit

- Target file: `scripts/init.py`
- Entry point: `select_indexes(workload_manifest)`

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
pip install -r benchmarks/ComputerSystems/DuckDBIndexSelection/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/ComputerSystems/DuckDBIndexSelection/verification/evaluator.py \
  benchmarks/ComputerSystems/DuckDBIndexSelection/scripts/init.py \
  --metrics-out /tmp/DuckDBIndexSelection_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/DuckDBIndexSelection \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
