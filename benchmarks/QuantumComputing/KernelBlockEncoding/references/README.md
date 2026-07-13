# References and scope

This benchmark implements an original, dependency-free evaluator around the
published FABLE construction. It does not vendor the authors' Qiskit or MATLAB
implementations.

## Block encodings and QML

- Gilyén, Su, Low, and Wiebe,
  [*Quantum singular value transformation and beyond*](https://arxiv.org/abs/1806.01838),
  define the block-encoding/QSVT framework and include quantum machine-learning
  applications.
- Nguyen, Kiani, and Lloyd,
  [*Block-encoding dense and full-rank kernels using hierarchical matrices*](https://arxiv.org/abs/2201.11329),
  explain why generic efficient access is a strong assumption for dense kernel
  matrices and study structure-aware alternatives.

## Circuit constructions

- Camps and Van Beeumen,
  [*FABLE: Fast Approximate Quantum Circuits for Block-Encodings*](https://arxiv.org/abs/2205.00081),
  give the Walsh-Hadamard/Gray-code uniformly controlled rotation construction and
  its compression rule. The authors' reference repository is
  [QuantumComputingLab/fable](https://github.com/QuantumComputingLab/fable).
- Kuklinski and Rempfer,
  [*S-FABLE and LS-FABLE*](https://arxiv.org/abs/2401.04234), introduce Hadamard
  conjugation as a way to expose compressible structure. This benchmark generalizes
  that discrete choice to any subset of system qubits.
- Clader et al.,
  [*Quantum Resources Required to Block-Encode a Matrix of Classical Data*](https://arxiv.org/abs/2206.03505),
  demonstrate why circuit count/depth and data-loading resources must be made
  explicit rather than hidden behind a matrix oracle.

## Benchmark boundary

The score is a logical construction cost, not a claim about one physical quantum
processor. The frozen weights make normalization, arbitrary rotations, CNOTs, and
depth jointly visible and reproducible. Fault-tolerant synthesis, hardware routing,
noise, and alternative block-encoding families are useful future extensions but
are deliberately outside this first task.
