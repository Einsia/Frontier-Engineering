# Agent-Evolve Quantum Tasks

This folder contains four benchmark-driven optimization tasks. Tasks 01-03 optimize circuits and
are built on this repository's `mqt.bench` APIs; task 04 is a classical decoder for a quantum
error-correcting code and does not use `mqt.bench`.

## Environment

Tasks 01-03 use the requested interpreter:

```bash
pip install mqt.bench
```

Task 04 needs its own evaluator dependencies (Stim + PyMatching); see
`task_04_quantum_error_decoder/README.md`.

## Task List
- `task_01_routing_qftentangled`: mapped-level routing optimization on IBM Falcon.
- `task_02_clifford_t_synthesis`: native-gates (`clifford+t`) synthesis optimization.
- `task_03_cross_target_qaoa`: one strategy evaluated on both IBM and IonQ targets.
- `task_04_quantum_error_decoder`: surface-code decoder scored against minimum-weight perfect
  matching (logical error rate, uncapped above the anchor).

Current baseline strategies:
- `task_01`: local rewrite preprocessing followed by target-aware multi-seed transpile search.
- `task_02`: `local rewrite -> clifford+t transpile(opt=3) -> local rewrite`.
- `task_03`: target-aware transpilation with backend-specific equivalence registration and transpile settings.
- `task_04`: never predicts a logical flip (legal, and scores 0.0 by construction).

## Unified Per-Task Structure
Each task uses the same structure:
- `baseline/solve.py`: evolve entrypoint with the task-specific baseline strategy.
- `baseline/structural_optimizer.py`: task-local local-rewrite helper reused by `solve.py` (tasks 01-03).
- `verification/evaluate.py`: single evaluation entrypoint.
- `verification/utils.py`: helper functions (tasks 01-03).
- `tests/case_*.json`: differentiated test cases (tasks 01-03).
- `README*.md` and `TASK*.md`: run guide and task definition.

Task 04 additionally ships `verification/candidate_runner.py`, which loads the candidate decoder
in a separate interpreter that never receives the true observable flips.

## Eval
```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_01_routing_qftentangled task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_02_clifford_t_synthesis task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_03_cross_target_qaoa task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_04_quantum_error_decoder task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
```