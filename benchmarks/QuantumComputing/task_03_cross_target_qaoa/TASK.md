# Task 03: Cross-Target Robust Optimization (QAOA)

## Goal
Optimize QAOA circuits so one strategy works on both:
- `ibm_falcon_27`
- `ionq_aria_25`

Each case is evaluated on both targets to reduce single-device overfitting.

## Editable Scope
- Only edit `baseline/solve.py`.

## Evaluation Pipeline
For each case, the evaluator:
1. Builds an algorithm-level QAOA circuit (`BenchmarkLevel.ALG`) with case `seed` and `repetitions`.
2. Calls `optimize_circuit(input_circuit, target, case)` for each target in `case["targets"]`.
3. Canonicalizes candidate output (`optimization_level=0`) per target for fair scoring.
4. Generates mapped-level references at `opt_level=0..3` per target.
5. Reports candidate vs references and computes normalized score for each `(case, target)` pair.

## Input / Output Interface
`baseline/solve.py` must provide:

```python
def optimize_circuit(input_circuit, target, case):
    ...
    return optimized_circuit
```

Input:
- `input_circuit`: Qiskit `QuantumCircuit` generated from case config.
- `target`: Qiskit `Target` for current hardware target.
- `case`: dict from `tests/case_*.json`; evaluator adds `target_name` when calling solver.

Output:
- `optimized_circuit`: Qiskit `QuantumCircuit`.

## Correctness Gate (checked before any metric)

Your circuit is verified against the input circuit *before* depth and gate
counts are computed. A circuit that fails is not scored at all: the run is
marked invalid, not merely given a low score.

- Method: statevector sampling. `|0...0>` plus 4 Haar-random input states are
  evolved through both circuits and compared; the worst per-state fidelity must
  exceed `1 - 1e-9`.
- Global phase is ignored. So is the qubit permutation a routing pass
  introduces -- as long as your circuit declares it (see below).
- Rejected: the empty circuit, circuits that fail the fidelity threshold,
  `reset`, mid-circuit measurement, classically conditioned operations, and
  any circuit touching more than 22 qubits.

## Qubit Layout

QAOA circuits at ALG level carry no measurements, so the scorer cannot recover
the routing permutation from the circuit itself. If you return a circuit wider
than the input, it must carry the transpiler's layout. Returning what
`transpile()` produced is enough; if you post-process it, preserve
`circuit._layout` (`baseline/structural_optimizer.py` already does). A
same-width circuit with no layout is read as the identity mapping. The declared
layout is a hint, not an authority: a permutation you declare but did not
implement fails the check.

## Execution Model

`baseline/solve.py` runs in its own interpreter. The input circuit reaches you
as OpenQASM 3, and your returned circuit is exported to OpenQASM 3 and
re-parsed by the scorer, which computes the circuit metrics.

## Cost and Score
Cost function:
- `cost = two_qubit_count + 0.2 * depth`

Normalized score:
- `score_0_to_3 = 3 * (opt0_cost - x_cost) / (opt0_cost - opt3_cost)`

Interpretation:
- `opt=0` reference has score `0`.
- `opt=3` reference has score `3`.
- Candidate uses the same scale for each target.

## Test Cases
Each case is expanded to two targets (`ibm_falcon_27`, `ionq_aria_25`):
- `cross_target_case_01` (`tests/case_01.json`): `benchmark=qaoa`, `num_qubits=10`, `repetitions=2`, `seed=11`
- `cross_target_case_02` (`tests/case_02.json`): `benchmark=qaoa`, `num_qubits=12`, `repetitions=2`, `seed=17`
- `cross_target_case_03` (`tests/case_03.json`): `benchmark=qaoa`, `num_qubits=14`, `repetitions=3`, `seed=31`

Total evaluated pairs: 6.

## Current Baseline (`baseline/solve.py`)
Rule-based structural rewrites without directly calling `transpile`:
1. barrier removal
2. adjacent inverse/self-inverse cancellation
3. adjacent parameterized-rotation merge

## Saved Artifacts
Each run saves to `runs/eval_<timestamp>/`.

Per `(case, target)` pair artifacts include:
- `input.qasm` + `input.png`
- `candidate_raw.qasm` + `candidate_raw.png`
- `candidate_canonical.qasm`
- `reference_opt_0.qasm`
- `reference_opt_1.qasm`
- `reference_opt_2.qasm`
- `reference_opt_3.qasm`
