# FT10 Neighborhood Move Selection

Rank adjacent-swap moves for a frozen local-search shell on the canonical FT10 job shop and minimize makespan.

## Why This Benchmark Matters

This benchmark models schedule refinement under a limited search budget. The scheduler already has a feasible incumbent; what matters is which neighboring move it tries first.

You are controlling move ranking inside a fixed local-search loop rather than searching the schedule space end to end yourself.

## What You Edit

- Target file: `scripts/init.py`
- Entry point: `score_move(move, state)`

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
pip install -r benchmarks/OperationsResearch/FT10NeighborhoodMoveSelection/verification/requirements.txt
```

## Quick Run

From repository root:

```bash
python benchmarks/OperationsResearch/FT10NeighborhoodMoveSelection/verification/evaluator.py \
  benchmarks/OperationsResearch/FT10NeighborhoodMoveSelection/scripts/init.py \
  --metrics-out /tmp/FT10NeighborhoodMoveSelection_metrics.json
```

## Optional: Run with `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/FT10NeighborhoodMoveSelection \
  algorithm.iterations=0
```

If you need a non-default interpreter, also add `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`.

<!-- AI_GENERATED -->
