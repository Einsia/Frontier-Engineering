# MBB Beam Topology Optimization

Update densities inside a frozen half-MBB pyMOTO topology-optimization loop and minimize final compliance.

## Why This Benchmark Matters

The half-MBB beam is a classic stiffness-per-material benchmark. Local density tweaks can help or hurt global load paths, so the update rule has to reason beyond a single element neighborhood.

The task is again optimizer design under repeated constrained calls: you control the update rule, while the physics loop and feasibility checks stay fixed.

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
pip install -r benchmarks/StructuralOptimization/MBBBeamTopologyOptimization/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/StructuralOptimization/MBBBeamTopologyOptimization/verification/evaluator.py \
  benchmarks/StructuralOptimization/MBBBeamTopologyOptimization/scripts/init.py \
  --metrics-out /tmp/MBBBeamTopologyOptimization_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=StructuralOptimization/MBBBeamTopologyOptimization \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
