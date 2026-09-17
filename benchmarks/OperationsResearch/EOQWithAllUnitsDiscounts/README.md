# EOQ with All-Units Discounts

Choose an order quantity for frozen EOQ cases with all-units discounts and minimize average annual cost.

## Why This Benchmark Matters

All-units discounts appear in packaging, chemicals, and contract manufacturing. Crossing a breakpoint changes the unit price of every unit in the order, so choosing the wrong region can dominate annual spend.

This is a frozen piecewise optimization problem with regime switches. The output is still a single scalar `Q`, but the objective changes discontinuously when the chosen price region changes.

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
pip install -r benchmarks/OperationsResearch/EOQWithAllUnitsDiscounts/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/EOQWithAllUnitsDiscounts/verification/evaluator.py \
  benchmarks/OperationsResearch/EOQWithAllUnitsDiscounts/scripts/init.py \
  --metrics-out /tmp/EOQWithAllUnitsDiscounts_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/EOQWithAllUnitsDiscounts \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
