# Poisson (r,Q) with Service-Level Constraint

Choose `(r, Q)` policies for frozen Poisson-demand inventory cases with a hard service-level target and minimize average cost.

## Why This Benchmark Matters

This benchmark models replenishment for spare parts and MRO inventory, where demand arrives as discrete events and service commitments still matter. Good policies cut stockouts without overspending on safety stock.

It is a small stochastic-policy tuning problem: the evaluator freezes the demand model and cost accounting, and your code only chooses the `(r, Q)` pair.

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
pip install -r benchmarks/OperationsResearch/PoissonRQServiceLevel/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/PoissonRQServiceLevel/verification/evaluator.py \
  benchmarks/OperationsResearch/PoissonRQServiceLevel/scripts/init.py \
  --metrics-out /tmp/PoissonRQServiceLevel_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/PoissonRQServiceLevel \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
