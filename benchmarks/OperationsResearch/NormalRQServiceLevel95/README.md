# Normal (r,Q) with 95% Service-Level Constraint

Choose `(r, Q)` policies for frozen Normal-demand inventory cases with a hard 95% service-level target and minimize average cost.

## Why This Benchmark Matters

This benchmark captures policy tuning near a service-level boundary. Small changes in reorder point can materially change stockout risk and working capital when the target is fixed around 95%.

Algorithmically, it is a small constrained discrete optimization problem over a frozen probabilistic model.

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
pip install -r benchmarks/OperationsResearch/NormalRQServiceLevel95/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/NormalRQServiceLevel95/verification/evaluator.py \
  benchmarks/OperationsResearch/NormalRQServiceLevel95/scripts/init.py \
  --metrics-out /tmp/NormalRQServiceLevel95_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/NormalRQServiceLevel95 \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
