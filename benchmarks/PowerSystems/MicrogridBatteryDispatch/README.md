# MicrogridBatteryDispatch

Optimize battery dispatch for a grid-connected commercial microgrid with solar PV,
time-varying tariffs, demand charges, round-trip losses, and degradation cost.

## Files

- `Task.md`: task contract, model, and scoring details.
- `scripts/init.py`: editable seed policy used by agents.
- `verification/evaluator.py`: deterministic simulator and scorer.
- `verification/requirements.txt`: evaluator dependencies.
- `frontier_eval/`: unified-task metadata.

## Candidate Interface

Edit `scripts/init.py` only. The evaluator imports:

```python
dispatch_action(state: dict) -> float
```

The returned value is battery power in kW. Positive values discharge the battery
to serve load, and negative values charge the battery. The evaluator enforces
all physical limits and penalizes requests that exceed feasible charge or
discharge bounds.

## Quick Run

From this directory:

```bash
python verification/evaluator.py scripts/init.py
```

From the repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=PowerSystems/MicrogridBatteryDispatch \
  algorithm=openevolve \
  algorithm.iterations=0
```

No GPU, Docker, API key, or external assets are required.
