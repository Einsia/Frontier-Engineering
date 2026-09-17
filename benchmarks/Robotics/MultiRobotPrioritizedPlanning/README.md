# Multi-Robot Prioritized Planning

Plan collision-free paths for three robots on a frozen grid while minimizing total path cost.

## Why This Benchmark Matters

This benchmark models small-fleet coordination in shared aisles. Good path sets reduce blocking and deadlocks without inflating overall travel cost.

This is small-scale multi-agent path finding: single-agent shortest paths are easy, but coordinating several paths without vertex or edge conflicts is the real challenge.

## What You Edit

- Target file: `scripts/init.py`
- Entry point: `plan_paths(grid, starts, goals)`

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
pip install -r benchmarks/Robotics/MultiRobotPrioritizedPlanning/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/Robotics/MultiRobotPrioritizedPlanning/verification/evaluator.py \
  benchmarks/Robotics/MultiRobotPrioritizedPlanning/scripts/init.py \
  --metrics-out /tmp/MultiRobotPrioritizedPlanning_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Robotics/MultiRobotPrioritizedPlanning \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
