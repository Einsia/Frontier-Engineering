# Wake Steering Control

This benchmark asks an agent to improve a deterministic yaw-control policy for
a nine-turbine wind farm. A frozen FLORIS 4.6.6 verifier evaluates the policy
over multiple wind directions and speeds.

## Structure

```text
scripts/init.py                 editable yaw policy
references/farm_config.json     public farm and score contract
verification/evaluator.py       frozen FLORIS evaluator
verification/run_candidate.py   isolated candidate runner
frontier_eval/                  unified-task metadata
baseline/result_log.json        measured zero-yaw baseline
```

## Environment

From the Frontier-Engineering repository root, create the task runtime. The task
is tested with Python 3.12 on Linux.

```bash
python3.12 -m venv .venvs/frontier-wake-steering
.venvs/frontier-wake-steering/bin/python -m pip install \
  -r benchmarks/WindEnergy/WakeSteeringControl/verification/requirements.txt
```

The task is CPU-only, and FLORIS itself does not require a GPU. A baseline
evaluation typically completes within seconds. No external dataset, Docker, or
runtime network access is required.

## Direct Evaluation

From this benchmark directory:

```bash
../../../.venvs/frontier-wake-steering/bin/python \
  verification/evaluator.py scripts/init.py
```

The evaluator writes `metrics.json` and `artifacts.json`. The shipped zero-yaw
policy is feasible and has a combined score of approximately zero by design.

## Unified Evaluation

The unified benchmark ID is `WindEnergy/WakeSteeringControl`:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=WindEnergy/WakeSteeringControl \
  task.runtime.python_path=uv-env:frontier-wake-steering \
  algorithm=openevolve \
  algorithm.iterations=0
```

Optimization runs require the normal model API configuration used by
Frontier Eval. Baseline-only validation does not require an API key.

## Reproducibility and Security

- FLORIS is pinned to version 4.6.6.
- The verifier uses the built-in NREL 5 MW turbine model and a fixed farm.
- Candidate code runs in a separate subprocess with a wall-clock timeout.
- The unified task checks the verifier and public contract as read-only and
  invalidates candidates that modify them.
- Process isolation is not a hardened security sandbox. Run untrusted candidate
  code in a container or disposable host.
