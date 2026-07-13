# AGVWarehouseRouting

Optimize the pick sequence for an automated guided vehicle (AGV) in warehouse
aisles with obstacles, congestion zones, turn penalties, and route-length limits.

## Files

- `Task.md`: task contract and scoring details.
- `scripts/init.py`: editable seed routing heuristic.
- `verification/evaluator.py`: deterministic route simulator and scorer.
- `verification/requirements.txt`: evaluator dependencies.
- `frontier_eval/`: unified-task metadata.

## Candidate Interface

Edit `scripts/init.py` only. The evaluator imports:

```python
plan_order(instance: dict) -> list[int]
```

The returned list must contain every pick id exactly once. The evaluator computes
the least-cost path between consecutive stops on the fixed grid and scores the
resulting total travel cost.

## Quick Run

From this directory:

```bash
python verification/evaluator.py scripts/init.py
```

From the repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Robotics/AGVWarehouseRouting \
  algorithm=openevolve \
  algorithm.iterations=0
```

No GPU, Docker, API key, or external assets are required.
