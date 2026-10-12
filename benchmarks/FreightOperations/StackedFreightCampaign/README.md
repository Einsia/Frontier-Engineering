# StackedFreightCampaign

See [Task.md](Task.md) for the model, constraints, input schema and candidate interface.
Inputs live in `environment/data`; `solution` contains the baseline source library;
`scripts/init.py` is the editable Python entry point; `verification` owns all checks.

## Requirements

Linux with user namespaces and bubblewrap; Python 3.12; g++ (C++20 supported),
Boost program_options, NumPy 2.2.6 for maintenance, and Java 17+ for freight.
Use one CPU and 16 GiB RAM. Candidate generation has a 900-second cap including
compilation. No commercial solvers, external accounts, model keys or network
access are needed. The initial program regenerates outputs from inputs.

## Validation

From this task directory:

```bash
python verification/evaluator.py scripts/init.py
```

From the repository root after setting up the Frontier Eval driver:

```bash
python -m frontier_eval task=unified task.benchmark=FreightOperations/StackedFreightCampaign algorithm=openevolve algorithm.iterations=0 task.runtime.python_path=python3 algorithm.oe.evaluator.timeout=1200
```

The timeout override covers candidate generation and independent checking.
`metrics.json` reports validity, raw objective, continuous score and output hashes.
Lower raw objective is better; the framework maximizes its negative. The input
is public and no hidden quality threshold is imposed. This is a generative
optimization task, not evidence of single-shot frontier-model difficulty.

A Docker definition is provided under `verification/docker`; build from the
repository root and select this file with `docker build -f`. The host must allow
nested user namespaces for bubblewrap. Container execution is not claimed until tested.

Input and processing details are in [references/source.md](references/source.md). Third-party attribution and reuse information are in [references/THIRD_PARTY_NOTICES.md](references/THIRD_PARTY_NOTICES.md).

## Verified baseline

Two fresh generations (direct evaluator and unified zero-iteration run) passed
with identical output hashes and raw objective 2457693.0.
The unified evaluation took 8.7 seconds in the validation environment.
See `references/validation.json`. The driver ran in a separate virtual environment;
`task.runtime.python_path=python3` selected the task runtime with NumPy 2.2.6.
No model API call or new optimization experiment was made.
