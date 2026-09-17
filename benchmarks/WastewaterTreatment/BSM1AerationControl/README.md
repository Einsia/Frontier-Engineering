# BSM1 Aeration Control

Design a deterministic feedback controller for an activated-sludge plant derived from the
IWA Benchmark Simulation Model No. 1 (BSM1). The controller sets oxygen-transfer coefficients
in the three aerobic reactors and the internal recycle flow. It must balance effluent quality,
energy, compliance, and actuator smoothness across dry, rain, and storm scenarios.

Edit only the EVOLVE-BLOCK in `scripts/init.py`, preserving:

```python
def reset_controller(scenario: dict) -> None: ...
def control(observation: dict) -> dict: ...
```

## Setup

The task is offline and CPU-only:

```bash
python -m pip install -r verification/requirements.txt
```

No raw IWA influent files are redistributed. The evaluator generates deterministic trajectories
from published BSM1 averages and weather-event descriptions. A complete baseline run takes about
45 seconds on a laptop.

## Direct evaluation

```bash
python verification/evaluator.py scripts/init.py --metrics-out metrics.json --artifacts-out artifacts.json
```

## Regression tests

```bash
python -m unittest discover -s verification -p "test_*.py" -v
```

## Unified evaluation

From the repository root:

```bash
python -m frontier_eval task=unified task.benchmark=WastewaterTreatment/BSM1AerationControl algorithm=openevolve algorithm.iterations=0
```

The ranking metric is `combined_score` (higher is better). `metrics.json` contains the aggregate
score and validity fields; `artifacts.json` contains scenario-level engineering metrics and daily
effluent samples. Candidate code runs in a separate, bounded JSON-lines worker process. This is
process isolation, not an operating-system security sandbox.

See `Task.md` for the exact interface and scoring model, and
`references/design_notes.md` for provenance, validation, and modelling limitations.
