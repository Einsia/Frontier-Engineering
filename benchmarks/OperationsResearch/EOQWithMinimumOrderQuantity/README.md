# EOQ with Minimum Order Quantity

Choose an order quantity for frozen deterministic EOQ cases with a hard minimum order quantity and minimize average annual cost.

## Why This Benchmark Matters

Supplier MOQs are a routine constraint in procurement. They change working-capital usage and warehouse occupancy, and they often push the feasible optimum onto a boundary that a naive EOQ formula misses.

This is a small constrained optimization problem over a frozen analytic cost model. The important part is boundary-aware decision logic, not systems integration.

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
pip install -r benchmarks/OperationsResearch/EOQWithMinimumOrderQuantity/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/EOQWithMinimumOrderQuantity/verification/evaluator.py \
  benchmarks/OperationsResearch/EOQWithMinimumOrderQuantity/scripts/init.py \
  --metrics-out /tmp/EOQWithMinimumOrderQuantity_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/EOQWithMinimumOrderQuantity \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
