# Adaptive Compressed Telemetry Execution

This CPU benchmark co-designs a telemetry column format and the operators that
consume it. Candidate C++ code encodes five correlated columns into opaque blocks,
decodes them losslessly, and answers exact filters and conditional sums directly
from those blocks. The evaluator compiles and runs the candidate, measures real
CPU time, checks every decoded byte and query answer, and reports both absolute
performance and a public cost-per-logical-TiB objective.

The task is motivated by the CPU and representation-efficiency requirements in the
[OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
and by recent work on composable, query-aware formats such as
[FastLanes](https://vldb.org/pvldb/vol18/p4629-afroozeh.pdf).

## Files

- `Task.md`: full API, workload, correctness, measurement, and scoring contract.
- `references/problem_config.json`: public execution, pricing, and scenario settings.
- `scripts/init.cpp`: editable raw-column starter implementation.
- `baseline/solution.cpp`: immutable copy of the raw starter.
- `baseline/result_log.txt`: recorded starter measurement.
- `verification/codec_api.h`: immutable candidate ABI.
- `verification/benchmark_driver.cpp`: immutable timed C++ driver.
- `verification/evaluator.py`: dataset generator, compiler, oracle, and scorer.
- `verification/test_evaluator.py`: end-to-end and integrity regression tests.
- `frontier_eval/`: unified-task metadata.

## Requirements

- Python 3.10 or newer; only the standard library is used.
- `g++` with C++20 support.
- A Linux-like host for CPU affinity and resource limits.

No database, service, network access, accelerator, or task-specific Python package
is required. The driver pins each timed process to one available CPU.

## Direct evaluation

From this task directory:

```bash
python verification/evaluator.py scripts/init.cpp
```

The uncompressed starter must be correct and scores exactly `1.0`. Measurements
vary by CPU, but the evaluator measures the immutable baseline in the same run for
every changed candidate. A score above `1.0` reduces the modeled monthly cost using
measured storage bytes and CPU time.

Compilation deliberately uses `-march=native`. Absolute throughput, modeled cost,
and candidate-to-baseline ratios can therefore vary across CPU models and compiler
versions. Compare leaderboard runs only within the same evaluation host and
environment; the co-measured immutable baseline controls within-run comparisons.

To retain detailed measurements:

```bash
python verification/evaluator.py scripts/init.cpp \
  --metrics-out metrics.json --artifacts-out artifacts.json
```

## Unified evaluation

From the repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/AdaptiveCompressedTelemetryExecution \
  algorithm=openevolve \
  algorithm.iterations=0
```

## Editing contract

Only edit the code between `EVOLVE-BLOCK-START` and `EVOLVE-BLOCK-END` in
`scripts/init.cpp`. Preserve the function signatures in `verification/codec_api.h`.
The editable block may add standard or compiler-provided headers, helpers, metadata,
adaptive encoding selection, SIMD code, and any self-contained block representation.
