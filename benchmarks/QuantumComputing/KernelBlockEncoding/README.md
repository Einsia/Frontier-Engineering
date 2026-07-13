# Kernel Block Encoding

This benchmark asks a C++ policy to construct compressed FABLE-style quantum
circuits for fixed-point kernel and Gram matrices used in machine learning. A
candidate chooses a partial-Hadamard basis, normalization, and sparse quantized
rotation vector. The independent evaluator analytically reconstructs the encoded
matrix, enforces the approximation budget, and applies a frozen gate compiler and
resource objective.

This is a circuit-construction task, not QML training or state-vector simulation.
The candidate directly changes the block encoding that is measured.

## Files

- `Task.md`: mathematical contract, C++ API, resource model, workloads, and score.
- `references/problem_config.json`: frozen kernels, limits, and objective weights.
- `references/README.md`: research and construction references.
- `scripts/init.cpp`: editable C++17 starter policy.
- `verification/construction_runtime.hpp`: immutable candidate-side construction API.
- `verification/evaluator.py`: independent workload generator, certificate checker,
  analytic block reconstruction, frozen resource compiler, and scorer.
- `verification/limited_exec.py`: thread-safe POSIX hard-limit launcher for candidate
  processes.
- `baseline/solution.cpp`: frozen starter used for score normalization.
- `baseline/result_log.txt`: measured reference evaluation.
- `frontier_eval/`: unified-task metadata and evaluator wrapper.

## Requirements

- Linux or another POSIX environment with Python 3.10+;
- `g++` with C++17 support; and
- one CPU core with less than 1 GiB RAM.

There are no Python packages, downloads, containers, external solvers, GPUs,
Qiskit, or quantum simulators.

The complete frozen-starter evaluation takes about 2.8 seconds on the repository's
current AMD EPYC host, including two C++ compilations and twelve construction runs.

## Direct evaluation

From this task directory:

```bash
python verification/evaluator.py scripts/init.cpp \
  --metrics-out metrics.json --artifacts-out artifacts.json
```

The unmodified starter reports `valid=1.0` and `combined_score=1.0`. A score above
1.0 is an improvement over the frozen starter.

## Unified evaluation

From the repository root:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=QuantumComputing/KernelBlockEncoding \
  algorithm=openevolve \
  algorithm.iterations=0
```

## Editing contract

Only change code between `EVOLVE-BLOCK-START` and `EVOLVE-BLOCK-END` in
`scripts/init.cpp`. The evaluator byte-compares the immutable source prefix and
suffix against the frozen baseline before compiling a candidate.
