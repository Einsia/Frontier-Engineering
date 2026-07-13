# AdaptiveLinkScheduling

Optimize per-resource-block user scheduling, modulation/coding selection, and
transmit power for a small wireless downlink under queue, channel, latency, and
power-budget constraints.

## Files

- `Task.md`: task contract and scoring details.
- `scripts/init.py`: editable seed scheduler.
- `verification/evaluator.py`: deterministic link simulator and scorer.
- `verification/requirements.txt`: evaluator dependencies.
- `frontier_eval/`: unified-task metadata.

## Candidate Interface

Edit `scripts/init.py` only. The evaluator imports:

```python
schedule_frame(frame: dict) -> list[dict]
```

Return one decision per resource block. Each decision should contain:

```python
{"user": <int>, "mcs": <int>, "power_dbm": <float>}
```

## Quick Run

From this directory:

```bash
python verification/evaluator.py scripts/init.py
```

From the repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=CommunicationEngineering/AdaptiveLinkScheduling \
  algorithm=openevolve \
  algorithm.iterations=0
```

No GPU, Docker, API key, or external assets are required.
