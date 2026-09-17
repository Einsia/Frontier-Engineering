# Grid Path Planning with Obstacles

Plan a collision-free path on a frozen 2D occupancy grid with static obstacles and keep path cost low.

## Why This Benchmark Matters

This benchmark mirrors warehouse-like navigation with blocked aisles and shelves. A shorter valid path reduces cycle time, battery use, and congestion.

It is a graph-search problem on a frozen grid map. The evaluator already defines the graph, legality checks, and cost function; you only supply the path.

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
pip install -r benchmarks/Robotics/GridPathPlanningWithObstacles/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/Robotics/GridPathPlanningWithObstacles/verification/evaluator.py \
  benchmarks/Robotics/GridPathPlanningWithObstacles/scripts/init.py \
  --metrics-out /tmp/GridPathPlanningWithObstacles_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Robotics/GridPathPlanningWithObstacles \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
