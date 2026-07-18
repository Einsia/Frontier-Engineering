# Certified AIG Resynthesis

This benchmark asks an optimization policy to rewrite real combinational Boolean
networks represented as and-inverter graphs (AIGs). Each proposed small-cut
replacement is accepted only after exact truth-table equivalence checking and is
recorded as a replayable certificate. The score rewards fewer reachable AND nodes
and lower logic depth.

This is a synthesis benchmark, not a timing or traffic simulator: candidate code
directly changes the Boolean DAG that is measured. The independent Python checker
reconstructs every accepted transformation from the original AIG and certificate.

## Files

- `Task.md`: complete API, proof format, workloads, limits, and score.
- `references/problem_config.json`: frozen workload and resource configuration.
- `references/README.md`: standards and research context.
- `scripts/init.cpp`: compact editable C++ starter policy.
- `verification/rewrite_runtime.hpp`: immutable graph API and certificate runtime.
- `baseline/solution.cpp`: frozen starter used for score normalization.
- `baseline/result_log.txt`: measured reference run.
- `verification/evaluator.py`: workload construction, compilation, independent
  certificate replay, and scoring.
- `verification/test_evaluator.py`: end-to-end, adversarial-certificate, timeout,
  isolation, and source-integrity regression tests.
- `frontier_eval/`: unified-task metadata and its argument-safe evaluator wrapper.

## Requirements

- Linux or another POSIX environment with Python 3.10+;
- `g++` with C++17 support; and
- one CPU core and less than 2 GiB RAM.

There are no Python packages, containers, external solvers, downloads, GPUs, or
vendor EDA tools. The complete starter evaluation takes about 3.3 seconds on the
repository's current AMD EPYC host, including two C++ compilations and ten circuit
runs.

## Direct evaluation

From this task directory:

```bash
python verification/evaluator.py scripts/init.cpp
```

The starter must report `valid=1.0` and `combined_score=1.0`. A score above 1.0 is
an improvement over the frozen starter.

## Unified evaluation

From the repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ElectronicDesignAutomation/CertifiedAIGResynthesis \
  algorithm=openevolve \
  algorithm.iterations=0
```

No runtime override is required; the default process isolation and
`frontier-eval-driver` environment are sufficient.

## Editing contract

Only change code between `EVOLVE-BLOCK-START` and `EVOLVE-BLOCK-END` in
`scripts/init.cpp`. The evaluator byte-compares both immutable portions against
the frozen baseline before compiling a candidate.
