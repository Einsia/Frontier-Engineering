# Cantilever Compliance Topology Optimization

Update densities inside a frozen cantilever pyMOTO topology-optimization loop and minimize final compliance.

## Why This Benchmark Matters

This benchmark stands in for lightweight bracket and support design. With a fixed material budget, the objective is to make the cantilever as stiff as possible.

From a CS point of view, this is optimizer design inside a frozen FEM/SIMP loop rather than one-shot prediction.

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
pip install -r benchmarks/StructuralOptimization/CantileverComplianceTopologyOptimization/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/StructuralOptimization/CantileverComplianceTopologyOptimization/verification/evaluator.py \
  benchmarks/StructuralOptimization/CantileverComplianceTopologyOptimization/scripts/init.py \
  --metrics-out /tmp/CantileverComplianceTopologyOptimization_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=StructuralOptimization/CantileverComplianceTopologyOptimization \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
