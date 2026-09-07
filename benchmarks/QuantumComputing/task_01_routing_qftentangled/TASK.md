# Task 01: Routing-Oriented Optimization (QFT Entangled)

## Goal
Given target-independent input circuits, optimize them for `ibm_falcon_27` under mapped-level constraints.

This task uses multiple QFT-entangled cases to reduce single-case overfitting.

## Editable Scope
- Only edit `baseline/solve.py`.

## Evaluation Pipeline
For each case, the evaluator:
1. Builds an input circuit from MQT Bench at `BenchmarkLevel.INDEP`.
2. Calls `optimize_circuit(input_circuit, target, case)`.
3. Canonicalizes your output once via mapped transpilation (`optimization_level=0`) for fair scoring.
4. Generates direct MQT Bench references at mapped-level `opt_level=0..3`.
5. Reports candidate vs references and computes normalized score.

## Input / Output Interface
`baseline/solve.py` must provide:

```python
def optimize_circuit(input_circuit, target, case):
    ...
    return optimized_circuit
```

Input:
- `input_circuit`: Qiskit `QuantumCircuit` generated from case config.
- `target`: Qiskit `Target` for `ibm_falcon_27`.
- `case`: dict loaded from `tests/case_*.json`.

Output:
- `optimized_circuit`: Qiskit `QuantumCircuit`.

## Correctness Gate (checked before any metric)

Your circuit is verified against the input circuit *before* depth and gate
counts are computed. A circuit that fails is not scored at all: the run is
marked invalid, not merely given a low score.

- Method: statevector sampling. `|0...0>` plus 4 Haar-random input states are
  evolved through both circuits and compared; the worst per-state fidelity must
  exceed `1 - 1e-9`. (9/11/13-qubit inputs on a 27-qubit device are too large
  for an exact unitary comparison.)
- Global phase is ignored. So is the qubit permutation a routing pass
  introduces -- as long as your circuit declares it (see below).
- Your circuit must measure the same classical bits the input circuit measures;
  those measurements are what pin down where each input qubit ends up.
- Rejected: the empty circuit, a measurement-only circuit, a lossy
  `approximation_degree`, `reset`, mid-circuit measurement, classically
  conditioned operations, and any circuit touching more than 22 qubits.

## Qubit Layout

If you return a circuit wider than the input (i.e. mapped onto the 27-qubit
device), it must carry the transpiler's layout so the scorer knows which
physical qubit holds which input qubit. Returning what `transpile()` produced
is enough; if you post-process it, preserve `circuit._layout`
(`baseline/structural_optimizer.py` already does). A same-width circuit with no
layout is read as the identity mapping.

## Execution Model

`baseline/solve.py` runs in its own interpreter. The input circuit reaches you
as OpenQASM 3, and your returned circuit is exported to OpenQASM 3 and
re-parsed by the scorer before it is measured. Only the circuit crosses that
boundary, so overriding `count_ops`, `depth` or `size` changes nothing.

## Cost and Score
Cost function:
- `cost = two_qubit_count + 0.2 * depth`

Normalized score:
- `score_0_to_3 = 3 * (opt0_cost - x_cost) / (opt0_cost - opt3_cost)`

Interpretation:
- `opt=0` reference always has score `0`.
- `opt=3` reference always has score `3`.
- Candidate score is measured on the same scale (it may be below `0` or above `3` if candidate is worse/better than those anchors).

## Test Cases
- `routing_case_01` (`tests/case_01.json`): `benchmark=qftentangled`, `num_qubits=9`, `input_opt_level=0`, `target=ibm_falcon_27`
- `routing_case_02` (`tests/case_02.json`): `benchmark=qftentangled`, `num_qubits=11`, `input_opt_level=1`, `target=ibm_falcon_27`
- `routing_case_03` (`tests/case_03.json`): `benchmark=qftentangled`, `num_qubits=13`, `input_opt_level=2`, `target=ibm_falcon_27`

## Current Baseline (`baseline/solve.py`)
Rule-based structural rewrites without directly calling `transpile`:
1. barrier removal
2. adjacent inverse/self-inverse cancellation
3. adjacent parameterized-rotation merge

## Saved Artifacts
Each run saves to `runs/eval_<timestamp>/`.

Per case artifacts include:
- `input.qasm` + `input.png`
- `candidate_raw.qasm` + `candidate_raw.png`
- `candidate_canonical.qasm`
- `reference_opt_0.qasm`
- `reference_opt_1.qasm`
- `reference_opt_2.qasm`
- `reference_opt_3.qasm`
