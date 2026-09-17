# EOQ with Incremental Discounts

Choose an order quantity for frozen EOQ cases with incremental discounts and minimize average annual cost.

## Why This Benchmark Matters

Incremental discount contracts are common in industrial purchasing: only the units beyond each breakpoint get the lower price. Correctly reasoning about the cumulative tiered purchase cost matters just as much as choosing a good order size.

From a CS angle, this is again a small frozen search problem, but the cost accounting is cumulative across tiers rather than a simple breakpoint lookup.

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
pip install -r benchmarks/OperationsResearch/EOQWithIncrementalDiscounts/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/EOQWithIncrementalDiscounts/verification/evaluator.py \
  benchmarks/OperationsResearch/EOQWithIncrementalDiscounts/scripts/init.py \
  --metrics-out /tmp/EOQWithIncrementalDiscounts_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/EOQWithIncrementalDiscounts \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
