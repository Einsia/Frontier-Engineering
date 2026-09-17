# WaterDistribution/PumpScheduling

A CPU-only closed-loop pump-scheduling benchmark on EPANET Net3 through WNTR.
The unified benchmark ID is `WaterDistribution/PumpScheduling`.

## Environment

From the repository root, create the repository-owned task runtime. The task is
tested with Python 3.11 on Linux.

```bash
python3.11 -m venv .venvs/frontier-wntr
.venvs/frontier-wntr/bin/python -m pip install \
  -r benchmarks/WaterDistribution/PumpScheduling/verification/requirements.txt
```

## Direct evaluation

From the benchmark directory:

```bash
../../../.venvs/frontier-wntr/bin/python verification/evaluator.py \
  scripts/init.py --json-out metrics.json --artifacts-out artifacts.json
```

## Unified baseline evaluation

From the repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=WaterDistribution/PumpScheduling \
  task.runtime.python_path=uv-env:frontier-wntr \
  algorithm=openevolve \
  algorithm.iterations=0
```

Baseline-only validation does not require a model API key.

## Tests

From the benchmark directory:

```bash
../../../.venvs/frontier-wntr/bin/python -m pytest -q verification/tests
```

## Resources and execution assumptions

The evaluator uses three documented public scenarios and three frozen hidden
variants. It requires CPU only, WNTR 1.4.0 and its EPANET runtime; no GPU,
Docker, external dataset, or network access is required. The evaluator executes
on the host. Candidate controllers run in an isolated subprocess with only the
JSON causal-observation interface, but the evaluator itself should still be run
only from a trusted benchmark checkout.
