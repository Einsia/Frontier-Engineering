# WNTR Pump Scheduling Benchmark Design

## Objective

Add `WaterDistribution/PumpScheduling` to Frontier-Engineering as a unified
task. The task evolves a deterministic pump controller for EPANET Net3. The
controller must reduce electricity cost and peak power while maintaining water
pressure and tank recovery across multiple demand, tariff, and leak scenarios.

## Server Isolation

All work remains inside an isolated workspace:

```text
workspace/
├── repo/                  # isolated Frontier-Engineering clone
├── env/                   # task-specific Python environment
├── cache/                 # package/download cache
└── runs/                  # disposable experiment output
```

Run all setup, evaluation, and test processes with CPU affinity `64-73`.
Set `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, and
`NUMEXPR_NUM_THREADS` to `1`; use process-level parallelism only where tests
show it is safe. Do not read, write, move, or delete sibling agent directories.

## Benchmark Package

```text
repo/
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-07-13-wntr-pump-scheduling-design.md
└── benchmarks/
    └── WaterDistribution/
        ├── README.md
        ├── README_zh-CN.md
        └── PumpScheduling/
            ├── README.md
            ├── README_zh-CN.md
            ├── Task.md
            ├── Task_zh-CN.md
            ├── THIRD_PARTY_NOTICES.md
            ├── scripts/
            │   └── init.py
            ├── references/
            │   ├── scenario_schema.json
            │   ├── scenarios_public.json
            │   └── provenance.md
            ├── verification/
            │   ├── evaluator.py
            │   ├── rollout.py
            │   ├── scoring.py
            │   ├── scenario_loader.py
            │   ├── requirements.txt
            │   └── tests/
            │       ├── test_candidate_contract.py
            │       ├── test_evaluator_failures.py
            │       ├── test_reproducibility.py
            │       └── test_scoring.py
            └── frontier_eval/
                ├── initial_program.txt
                ├── candidate_destination.txt
                ├── eval_command.txt
                ├── eval_cwd.txt
                ├── agent_files.txt
                ├── copy_files.txt
                ├── readonly_files.txt
                ├── artifact_files.txt
                └── constraints.txt
```

Generated files such as `metrics.json`, `artifacts.json`, evaluator logs, caches,
and virtual environments are excluded from version control.

## Candidate Contract

The editable file is `scripts/init.py`. Keep exactly one evolution region using
`EVOLVE-BLOCK-START` and `EVOLVE-BLOCK-END`.

The candidate exports:

```python
def control(observation: dict) -> dict[str, float]:
    """Return one normalized speed in [0, 1] for every configured pump."""
```

The observation contains only causal information:

- current hour and tariff;
- current tank levels;
- recent minimum and mean pressure;
- recent pump state and energy;
- demand forecast for the next control interval;
- configured pump identifiers and bounds.

The evaluator rejects missing pumps, extra pumps, non-finite values, out-of-range
speeds, mutation of the observation, nondeterministic repeated calls, exceptions,
and calls exceeding the per-step timeout. Candidate code cannot access scenario
files, WNTR internals, the network model, future realized demand, or verifier
state.

## Hydraulic Rollout

Pin WNTR and its EPANET engine in `verification/requirements.txt`. Load the
package-provided Net3 model instead of copying an external network file into the
benchmark. Record the exact WNTR version, source URL, Revised BSD notice, and
EPANET MIT notice in `THIRD_PARTY_NOTICES.md`.

Use 24 one-hour control intervals. At each interval:

1. Build the observation from carried tank levels and previous results.
2. Call the candidate once under a timeout.
3. Apply constant pump speeds for the next hour.
4. Run a one-hour EPANET hydraulic simulation.
5. Carry terminal tank levels into the next interval.
6. Accumulate pump energy, pressure, tank, and switching metrics.

Use pressure-dependent demand where supported. Fix all random seeds and reset the
network between scenarios. Water quality is outside scope.

## Scenarios

`scenarios_public.json` contains three documented development scenarios:

1. nominal weekday demand with flat tariff;
2. morning/evening peaks with time-of-use tariff;
3. forecast error with shifted peak demand.

The frozen evaluator defines three additional evaluation scenarios that are not
listed in `agent_files.txt`:

1. high-demand stress day;
2. a bounded leak at a fixed junction and interval;
3. combined tariff spike, forecast error, and leak.

All parameters are deterministic and versioned. The task documentation explains
the scenario families without exposing evaluation values through Agent context or
artifacts.

## Feasibility

A scenario is feasible only when:

- every hydraulic solve converges;
- every candidate output satisfies its contract;
- critical-node pressure remains at or above `20 m`;
- every tank stays within the physical Net3 limits;
- terminal tank levels are no more than `0.25 m` below their initial levels;
- pump speeds remain in `[0, 1]`;
- the complete rollout finishes within the evaluator timeout.

Any infeasible scenario makes the whole candidate invalid. This prevents good
performance on easy scenarios from compensating for loss of service.

## Scoring

For each feasible scenario, compute four higher-is-better components normalized
against the shipped feasible baseline:

- energy-cost improvement: 55%;
- peak-power improvement: 20%;
- switching/speed-smoothness improvement: 10%;
- terminal tank recovery: 15%.

Clip each component to a documented bounded range before aggregation. Convert the
weighted result to `[0, 100]`. Aggregate scenario scores as:

```text
combined_score = 0.70 * mean(scenario_scores)
               + 0.30 * min(scenario_scores)
```

This rewards average efficiency while preserving robustness. The evaluator emits
numeric `valid` and `combined_score` in `metrics.json`. `artifacts.json` includes
bounded per-scenario summaries and failure diagnostics, but not hidden scenario
parameters or reference solutions.

## Baseline

Ship a deterministic rule-based controller that:

- starts pumps when aggregate tank storage is low;
- reduces pumping during expensive tariff intervals when storage permits;
- increases pumping when pressure or storage approaches a safety threshold;
- applies rate limits to avoid excessive speed changes.

The baseline must be feasible on every scenario while leaving measurable cost and
peak-power headroom. Calibrate thresholds using the public scenarios, then verify
feasibility on all frozen scenarios without adding scenario-specific branches.

## Unified Metadata

Use the following contract:

```text
initial_program.txt       -> scripts/init.py
candidate_destination.txt -> scripts/init.py
eval_command.txt          -> {python} verification/evaluator.py {candidate}
eval_cwd.txt              -> .
copy_files.txt            -> .
```

Expose only task documentation, the candidate, public scenario schema, public
scenarios, and constraints through `agent_files.txt`. Protect `verification/`,
`references/`, task contracts, notices, and evaluation metadata through
`readonly_files.txt`. Collect only bounded `metrics.json`, `artifacts.json`, and
the evaluator log.

## Error Handling and Security

- Execute candidates in a subprocess with a fixed timeout and sanitized
  environment.
- Disable network access when an available isolation mechanism supports it.
- Restrict candidate imports to the Python standard library plus NumPy if needed.
- Run each scenario from a fresh copied model.
- Treat non-convergence, timeout, invalid JSON, NaN/Inf, and readonly violations
  as invalid results with actionable artifacts.
- Never execute task code outside the agent-owned server directory during
  development.

The server lacks Docker, so validation uses host processes. The documentation
must state that candidate code is untrusted and that production evaluation should
use stronger process or container isolation.

## Validation

Run in this order with CPU affinity `64-73`:

1. Create the isolated Python 3.11 environment and install pinned dependencies.
2. Confirm Net3 loads and completes a nominal hydraulic simulation.
3. Run unit tests for candidate contract, scoring, reproducibility, and failures.
4. Run `python verification/evaluator.py scripts/init.py` twice and confirm
   identical metrics.
5. Run deliberately invalid candidates covering exceptions, timeout, NaN,
   missing pumps, and pressure failure.
6. Run the unified baseline-only command with `algorithm.iterations=0`.
7. Run the repository readonly metadata audit in strict mode.
8. Run a small real optimization only when model credentials are available and
   the user authorizes API spending.

## Acceptance Criteria

- The shipped baseline is feasible on all six scenarios.
- Repeated evaluation produces identical metrics within exact JSON equality for
  deterministic fields.
- At least one simple, non-scenario-specific controller improvement beats the
  baseline, demonstrating optimization headroom.
- Candidate exceptions and contract violations produce `valid=0` without
  crashing the batch runner.
- The unified zero-iteration run succeeds using only documented dependencies.
- The readonly audit passes.
- No file outside the isolated workspace is modified.
