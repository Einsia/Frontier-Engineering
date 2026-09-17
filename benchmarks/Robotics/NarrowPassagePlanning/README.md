# Narrow-Passage Planning

Plan a collision-free path through a frozen narrow-passage occupancy grid and keep path cost close to optimal.

## Why This Benchmark Matters

Narrow passages are a classic planning failure mode: a planner that looks reasonable in open space can still fail badly at doorways, single-cell corridors, and other bottlenecks.

This is still graph search, but the topology forces the useful path through a thin feasible corridor, so many locally plausible heuristics waste search effort or suggest illegal shortcuts.

## What You Edit

- Target file: `scripts/init.py`
- Entry point: `plan_path(grid, start, goal)`

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
pip install -r benchmarks/Robotics/NarrowPassagePlanning/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/Robotics/NarrowPassagePlanning/verification/evaluator.py \
  benchmarks/Robotics/NarrowPassagePlanning/scripts/init.py \
  --metrics-out /tmp/NarrowPassagePlanning_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Robotics/NarrowPassagePlanning \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
