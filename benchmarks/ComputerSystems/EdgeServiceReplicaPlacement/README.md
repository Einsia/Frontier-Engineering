# EdgeServiceReplicaPlacement

This is a CPU-only, deterministic benchmark for stateful edge-service replica
placement and traffic routing. A candidate implements a policy, not a one-shot allocation:

```python
def decide(observation: dict) -> dict:
    ...
```

The evaluator runs ten 24-period scenarios covering normal diurnal demand, regional
bursts, node-failure-plus-burst, cross-region link degradation, and post-failure traffic
migration. Scale-ups have a one-period cold start. The simulator independently computes
availability, P95/P99 latency estimates, SLA violations, compute cost, cross-region
traffic/cost, and recovery time.

## Direct validation

From this directory:

```bash
python verification/evaluator.py scripts/init.py \
  --metrics-out metrics.json --artifacts-out artifacts.json
python -m unittest discover -s verification -p "test_*.py" -v
```

## Unified zero-iteration validation

From repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/EdgeServiceReplicaPlacement \
  algorithm=openevolve \
  algorithm.iterations=0
```

On Windows, set `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` if the OpenEvolve dependency
otherwise uses the system GBK codec. This is an environment workaround, not a benchmark
requirement.

## Editable boundary

Only the EVOLVE-BLOCK in `scripts/init.py` is agent-editable. The worker receives JSON
observations and returns JSON actions. It runs in a fresh temporary process per scenario,
with bounded decision time and output size. This process boundary prevents ordinary
shared-state and protocol coupling; it is not a substitute for an operating-system
security sandbox.

See [Task.md](Task.md) for the interface and [references/design_notes.md](references/design_notes.md)
for model scope. Detailed review material is in
[docs/parameter_assumptions.md](docs/parameter_assumptions.md),
[docs/tiny_oracle.md](docs/tiny_oracle.md),
[docs/evaluator-threat-model.md](docs/evaluator-threat-model.md), and
[docs/scoring-calibration-report.md](docs/scoring-calibration-report.md).
