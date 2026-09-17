# Quantum Computing Benchmarks

This folder contains circuit construction, synthesis, routing, and cross-target
optimization tasks.

## Task list

- [`KernelBlockEncoding`](KernelBlockEncoding/): construct normalization- and
  resource-efficient FABLE circuits for fixed-point QML kernel matrices. Its
  evaluator is self-contained and CPU-only.
- `task_01_routing_qftentangled`: mapped-level routing optimization on IBM Falcon.
- `task_02_clifford_t_synthesis`: native-gates (`clifford+t`) synthesis optimization.
- `task_03_cross_target_qaoa`: one strategy evaluated on both IBM and IonQ targets.

The three historical `task_0*` benchmarks use this repository's `mqt.bench` APIs
and require the configured quantum environment. `KernelBlockEncoding` uses only
Python 3 and a C++17 compiler; it requires no quantum SDK or simulator.

## Historical MQT task structure

Current baseline strategies for the MQT-backed tasks:

- `task_01`: local rewrite preprocessing followed by target-aware multi-seed transpile search.
- `task_02`: `local rewrite -> clifford+t transpile(opt=3) -> local rewrite`.
- `task_03`: target-aware transpilation with backend-specific equivalence registration and transpile settings.

Each historical task uses the following structure:

- `baseline/solve.py`: evolve entrypoint with the task-specific baseline strategy.
- `baseline/structural_optimizer.py`: task-local local-rewrite helper reused by `solve.py`.
- `verification/evaluate.py`: single evaluation entrypoint that includes candidate and `opt0..opt3` references.
- `verification/utils.py`: helper functions.
- `tests/case_*.json`: multiple differentiated test cases.
- `README*.md` and `TASK*.md`: run guide and task definition.

## Evaluation

Kernel block encoding:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/KernelBlockEncoding algorithm=openevolve algorithm.iterations=0
```

MQT-backed tasks:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_01_routing_qftentangled task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_02_clifford_t_synthesis task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_03_cross_target_qaoa task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
```
