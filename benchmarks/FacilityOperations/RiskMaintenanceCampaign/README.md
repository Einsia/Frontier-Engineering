# RiskMaintenanceCampaign

See [Task.md](Task.md) for the model, constraints, input schema and candidate interface.
Inputs live in `environment/data`; `solution` contains the baseline source library;
`scripts/init.py` is the editable Python entry point; `verification` owns all checks.

## Requirements

Linux with user namespaces and bubblewrap; Python 3.12; g++ (C++20 supported),
Boost program_options, NumPy 2.2.6 for maintenance, and Java 17+ for freight.
Use one CPU and 16 GiB RAM. Candidate generation has a 900-second cap including
compilation. No commercial solvers, external accounts, model keys or network
access are needed. The initial program regenerates outputs from inputs.

## One-time dependency setup

Before running either validation command, execute from this task directory:

```bash
python scripts/setup_dependencies.py
python -m pip install -r verification/requirements.txt
```

The offline source archive contains nlohmann/json 3.11.2 and simdjson 0.9.2
at the immutable upstream commits listed in `references/dependencies.json`.
Setup verifies both the archive SHA-256 and every source file's hash. No network
is used by this setup step or candidate execution. Extracted files are ignored
by Git but copied as read-only baseline assets by Frontier Eval. Source licenses
remain in the task and dependency headers. The archive contains only unchanged
third-party library files, not task logic or saved solutions; it avoids exceeding
GitHub's 20,000-line pull-request diff limit. Remaining baseline source is its
compiler-resolved dependency closure.

## Validation

From this task directory:

```bash
python verification/evaluator.py scripts/init.py
```

From the repository root after setting up the Frontier Eval driver:

```bash
python -m frontier_eval task=unified task.benchmark=FacilityOperations/RiskMaintenanceCampaign algorithm=openevolve algorithm.iterations=0 task.runtime.python_path=python3 algorithm.oe.evaluator.timeout=1200
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
with identical output hashes and raw objective 2743.5078649237475.
The unified evaluation took 43.44 seconds in the validation environment.
See `references/validation.json`. The driver ran in a separate virtual environment;
`task.runtime.python_path=python3` selected the task runtime with NumPy 2.2.6.
No model API call or new optimization experiment was made.
