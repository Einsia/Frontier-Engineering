# LA16 Dispatching Rule Optimization

Design a greedy dispatching rule for the canonical LA16 Lawrence 10x10 job shop and minimize makespan.

## Why This Benchmark Matters

This benchmark is the same policy-design problem as FT10, but on the canonical LA16 bottleneck structure. Small local scoring changes can still produce large throughput differences.

You are again writing a local priority function inside a fixed scheduler rather than constructing the schedule yourself.

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
pip install -r benchmarks/OperationsResearch/LA16DispatchingRuleOptimization/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/LA16DispatchingRuleOptimization/verification/evaluator.py \
  benchmarks/OperationsResearch/LA16DispatchingRuleOptimization/scripts/init.py \
  --metrics-out /tmp/LA16DispatchingRuleOptimization_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/LA16DispatchingRuleOptimization \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
