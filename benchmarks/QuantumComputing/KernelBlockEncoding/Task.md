# Task: Kernel Block Encoding

## 1. Engineering problem

Many quantum linear-algebra and quantum machine-learning algorithms assume access
to a unitary whose leading block is a scaled approximation of a classical matrix.
General constructions exist, but the actual circuit can be dominated by data
loading, normalization, controlled rotations, and routing. Kernel matrices make
the issue concrete: they are dense, but their geometry can create exploitable
structure in a suitable basis.

This task exposes construction co-design directly. Given a real symmetric kernel
matrix, choose:

- a computational or partial-Hadamard basis;
- the block-encoding normalization;
- which uniformly controlled rotations to retain; and
- the value of every retained, quantized rotation.

The output is a concrete compressed FABLE construction. The evaluator does not run
a QML model and does not estimate quality from a state-vector sample. It
reconstructs the encoded block from the construction integers and computes the
resources of the corresponding frozen gate schedule.

## 2. Block-encoding family

Let `N = 2^n` and let `A` be an `N x N` fixed-point input matrix. A candidate first
selects an `n`-bit `basis_mask`. If bit `k` is set, a normalized Hadamard is applied
to qubit `k` on both sides of the matrix:

```text
B = H_mask A H_mask
```

The evaluator implements this transform with integer butterflies. Applying a
Hadamard on both matrix axes contributes an exact denominator of two, so no
floating-point matrix transform is needed.

The candidate then selects `s >= max_ij |B_ij|`. Define

```text
C_ij     = B_ij / s
theta_ij = 2 arccos(C_ij)
```

Flatten `theta` in row-major order. With `W` the unnormalized Walsh-Hadamard matrix
of order `N^2` and `P_G` the binary-reflected Gray permutation, the uniformly
controlled rotation coefficients are

```text
hat_theta = P_G (W / N^2) theta.
```

Every emitted coefficient is an integer number of
`pi / 268435456` radians. Omitted coefficients are exactly zero. The checker
inverts the Gray permutation and Walsh-Hadamard transform and obtains

```text
B_tilde_ij = s cos(theta_tilde_ij / 2).
```

The FABLE oracle, diffusion layers, row/system swap, and optional basis wrappers
therefore form a unitary `U` on `2n + 1` qubits whose leading block is
`A_tilde / (N s)`. Its normalization is

```text
alpha = N s.
```

The construction uses `n + 1` block-encoding ancillas and `n` system qubits.

## 3. Validity condition

For the system-register leading block of `U`, every workload requires

```text
|| A - alpha (<0^(n+1)| tensor I) U (|0^(n+1)> tensor I) ||_F <= epsilon.
```

The evaluator reconstructs the left-hand matrix directly. Since the spectral norm
is no greater than the Frobenius norm, every accepted construction also has
spectral block error at most `epsilon`.

Targets, basis transforms, scale bounds, Gray permutations, and quantized angle
transforms are independently recomputed in Python. Candidate-reported errors and
resource counts are ignored. A small explicit floating-point guard is added to the
computed trigonometric error before the validity comparison.

## 4. Candidate API

Only this function is editable:

```cpp
void optimize(kernel_block_encoding::Construction& construction);
```

The immutable class in `verification/construction_runtime.hpp` provides:

```cpp
std::size_t dimension() const;
std::size_t system_qubits() const;
std::size_t coefficient_count() const;
long double epsilon() const;
long double target(std::size_t row, std::size_t column) const;

void set_basis_mask(std::uint32_t mask);
std::int64_t minimum_scale_numerator() const;
void set_scale_numerator(std::int64_t numerator);
void set_scale_multiplier(long double multiplier);

std::vector<std::int64_t> exact_angle_ticks() const;
long double frobenius_error(const std::vector<std::int64_t>& ticks) const;
ResourceEstimate resources(const std::vector<std::int64_t>& ticks) const;
long double objective(const std::vector<std::int64_t>& ticks) const;
void commit(std::vector<std::int64_t> ticks);
```

Changing the basis resets the minimum scale. The scale numerator may range from the
new minimum through 16 times that minimum. `exact_angle_ticks()` produces the full
quantized FABLE vector for the current basis and scale; a policy may drop or alter
any tick before committing it. Helper error and resource methods support search,
but only the independent Python reconstruction determines the score.

## 5. Frozen circuit resources

The sparse coefficient vector is compiled with the compressed uniform-rotation
schedule:

1. traverse control states in binary-reflected Gray order;
2. emit one `RY` for each nonzero coefficient;
3. across a run of zero rotations, cancel repeated control toggles and emit one
   CNOT for each bit with odd transition parity;
4. close the Gray cycle;
5. add the two `n`-Hadamard diffusion layers and `n` register swaps; and
6. add two Hadamards for every selected basis qubit.

The reported counts are:

- arbitrary-angle `RY` rotations;
- oracle and total CNOTs, with each SWAP decomposed into three CNOTs;
- Hadamards;
- logical depth of the frozen schedule; and
- `2n + 1` logical qubits.

All oracle rotations and CNOTs touch the rotation target, so they are sequential in
this construction. The register swaps are disjoint and contribute three depth
layers.

## 6. Workloads

The evaluator deterministically generates six fixed-point matrices:

1. a 16-sample clustered anisotropic RBF kernel;
2. a 32-sample, higher-dimensional clustered RBF kernel;
3. a 32-sample degree-three polynomial Gram matrix;
4. a 32-sample rational-quadratic kernel;
5. a 32-node random-walk feature Gram matrix; and
6. a 64-sample mixture of two RBF length scales.

The RBF generators use high-precision decimal exponentiation before fixed-point
rounding. Polynomial, rational, and walk kernels use integer arithmetic. Input
bytes and SHA-256 digests are frozen in `references/problem_config.json` and
reported in `artifacts.json`.

## 7. Objective

For a valid construction, the frozen compiled cost is

```text
16 * RY + 1 * CNOT + 0.25 * H + 0.25 * depth.
```

The scenario objective is

```text
effective_cost = alpha * compiled_cost.
```

Multiplying by `alpha` makes normalization part of the optimization: a basis that
compresses strongly can still lose if its transformed maximum entry is large.

For scenario `i`:

```text
score_i = baseline_effective_cost_i / candidate_effective_cost_i.
```

`combined_score` is the geometric mean across all six scenarios. The direct-basis,
global-threshold starter is frozen as the baseline and scores exactly 1.0. Larger
is better.

The evaluator isolates workload failures and continues through the full suite. A
failed workload retains its baseline data and a workload-level error, while every
successful workload retains its independently checked score. `partial_combined_score`
is the geometric mean over those successful workloads and is diagnostic only. The
official `combined_score` remains zero and `valid=0.0` unless all six workloads
succeed, so skipping a difficult scenario can never improve the optimization
target.

## 8. Limits and reproducibility

- matrix dimensions are at most 64;
- scale is at most 16 times the basis-dependent minimum;
- angle certificates are at most 256 KiB;
- candidate source is at most 1 MB;
- candidate execution is limited to 5 seconds and 1 GiB per workload;
- candidate processes are subject to `RLIMIT_NPROC=64` where supported; and
- compilation uses `g++ -std=c++17 -O2`.

There is no network access, external solver, quantum SDK, simulator, container,
GPU, or downloaded data. Compilation is outside candidate execution time but is
included in evaluator wall time. Invalid source edits, malformed certificates,
timeouts, scale violations, or excessive block error produce `valid=0.0` and score
0.0.
