# Security-Constrained Dispatch

This benchmark asks an agent to improve generator active-power and voltage
setpoints across normal and N-1 operating scenarios derived from PGLib-OPF.
Every candidate is checked by an independent AC power-flow verifier.

## Benchmark ID

```text
PowerSystems/SecurityConstrainedDispatch
```

## Data provenance

The bundled MATPOWER cases come from PGLib-OPF release `v23.07`, commit
`dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3`:

- `pglib_opf_case24_ieee_rts.m`
- `pglib_opf_case57_ieee.m`
- `pglib_opf_case73_ieee_rts.m`

PGLib-OPF is maintained by the IEEE PES Task Force on Benchmarks for Validation
of Emerging Power System Algorithms. See `references/pglib/LICENSE` and
`references/PROVENANCE.md`.

## Environment

Use Python 3.12 on Linux. Install the pinned dependencies:

```bash
python3.12 -m venv .venvs/frontier-pglib-scd
.venvs/frontier-pglib-scd/bin/python -m pip install \
  -r benchmarks/PowerSystems/SecurityConstrainedDispatch/verification/requirements.txt
```

The evaluator is CPU-only and requires Linux seccomp support. Candidate code is
run in a restricted worker process; Docker and Linux namespaces are not used.
The worker blocks file access, process creation, and networking from `solve()`.
Because namespace isolation is unavailable on the target runtime, this is not
claimed to be container-equivalent isolation. Evaluation fails closed if the
seccomp filter cannot be installed.

A typical baseline evaluation of all 12 scenarios uses less than 2 GB RAM and
should complete within seconds on a modern CPU. Candidate import has a separate
10-second infrastructure timeout. Each `solve()` call retains its full
contract-defined two-second budget.

## Direct evaluation

From the benchmark directory:

```bash
../../../.venvs/frontier-pglib-scd/bin/python \
  verification/evaluator.py scripts/init.py \
  --metrics-out metrics.json \
  --artifacts-out artifacts.json
```

## Frontier Eval

From the repository root, use the repository-owned task runtime:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=PowerSystems/SecurityConstrainedDispatch \
  task.runtime.python_path=uv-env:frontier-pglib-scd \
  algorithm=openevolve \
  algorithm.iterations=0
```

Baseline-only validation does not require a model API key.

## Isolation tests

From the benchmark directory:

```bash
../../../.venvs/frontier-pglib-scd/bin/python -m pytest -q \
  verification/test_candidate_isolation.py
```

## Layout

- `scripts/init.py`: editable dispatch policy.
- `verification/`: frozen AC power-flow evaluator.
- `references/pglib/`: version-pinned PGLib source cases and license.
- `references/scenarios.json`: deterministic scenario baselines and reference costs.
- `references/build_scenarios.py`: reproducible scenario-generation script.
- `frontier_eval/`: unified-task metadata.

See `Task.md` for the complete contract and scoring definition.
