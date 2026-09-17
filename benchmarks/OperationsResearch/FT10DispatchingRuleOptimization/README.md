# FT10 Dispatching Rule Optimization

Design a greedy dispatching rule for the canonical FT10 Fisher-Thompson 10x10 job shop and minimize makespan.

## Why This Benchmark Matters

This benchmark stands in for online shop-floor dispatching, where lightweight priority rules are still used because they are easy to deploy and can materially change throughput and overtime.

You are not returning a full schedule. You are writing the priority function inside a frozen scheduler, so the task is policy design under a fixed simulator.

## What You Edit

- Target file: `scripts/init.py`
- Entry point: `score_operation(operation, state)`

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
pip install -r benchmarks/OperationsResearch/FT10DispatchingRuleOptimization/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/FT10DispatchingRuleOptimization/verification/evaluator.py \
  benchmarks/OperationsResearch/FT10DispatchingRuleOptimization/scripts/init.py \
  --metrics-out /tmp/FT10DispatchingRuleOptimization_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/FT10DispatchingRuleOptimization \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
