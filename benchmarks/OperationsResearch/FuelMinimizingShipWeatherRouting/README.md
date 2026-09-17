# Fuel-Minimizing Ship Weather Routing

Route a ship across a frozen coastal grid while minimizing fuel consumption under deterministic wind and current fields.

## Why This Benchmark Matters

This benchmark stands in for weather-aware voyage planning. The shortest geometric route is rarely the cheapest once headwind, crosswind, and current penalties are folded into the fuel model.

It is a constrained routing problem on a fixed grid graph whose edge costs are induced by environmental fields.

## What You Edit

- Target file: `scripts/init.py`
- Entry point: `solve(instance)`

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
pip install -r benchmarks/OperationsResearch/FuelMinimizingShipWeatherRouting/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/FuelMinimizingShipWeatherRouting/verification/evaluator.py \
  benchmarks/OperationsResearch/FuelMinimizingShipWeatherRouting/scripts/init.py \
  --metrics-out /tmp/FuelMinimizingShipWeatherRouting_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/FuelMinimizingShipWeatherRouting \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
