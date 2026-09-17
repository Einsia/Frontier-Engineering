# Bridge Topology Optimization

Update densities inside a frozen bridge-like pyMOTO topology-optimization loop and minimize final compliance.

## Why This Benchmark Matters

This benchmark models a bridge-like layout problem with a prescribed solid deck. Part of the structure is fixed up front, so the remaining material must form an efficient load path under a hard budget.

You are not drawing the final structure once. You are designing the inner update rule of a fixed PDE-constrained optimizer, and every step must remain feasible.

## What You Edit

- Target file: `scripts/init.py`
- Entry point: `update_density(density, sensitivity, state)`

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
pip install -r benchmarks/StructuralOptimization/BridgeTopologyOptimization/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/StructuralOptimization/BridgeTopologyOptimization/verification/evaluator.py \
  benchmarks/StructuralOptimization/BridgeTopologyOptimization/scripts/init.py \
  --metrics-out /tmp/BridgeTopologyOptimization_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=StructuralOptimization/BridgeTopologyOptimization \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
