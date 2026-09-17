# Dynamic-Current Minimum-Time Routing

Route a ship across a frozen coastal grid while minimizing travel time under deterministic current and depth constraints.

## Why This Benchmark Matters

This benchmark stands in for channel navigation and port-access planning. A fast route improves schedule reliability, but the shortest geometric route can be illegal or slow once current assistance and draft limits matter.

Algorithmically, it is a constrained shortest-path problem on a fixed grid graph with physics-induced edge costs.

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
pip install -r benchmarks/OperationsResearch/DynamicCurrentMinimumTimeRouting/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/DynamicCurrentMinimumTimeRouting/verification/evaluator.py \
  benchmarks/OperationsResearch/DynamicCurrentMinimumTimeRouting/scripts/init.py \
  --metrics-out /tmp/DynamicCurrentMinimumTimeRouting_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/DynamicCurrentMinimumTimeRouting \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
