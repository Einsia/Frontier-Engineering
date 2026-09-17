# Task: Capacitated Vehicle Routing Problem (CVRP)

## Audience and assumptions

This task assumes a general CS background but no (or little) prior exposure to
combinatorial optimization / vehicle routing.

## Background

In logistics, trucks depart from a warehouse to deliver goods to customers. The
**capacitated vehicle routing problem (CVRP)** is its standard mathematical
model:

- **Depot**: node 0; every vehicle starts and ends here.
- **Customers**: nodes 1..n, each with a demand `demand[c]`.
- **Vehicles**: identical, capacity limit `capacity`.
- **Route**: a sequence `depot → some customers → depot` whose total demand
  does not exceed `capacity`.

Goal: serve **all** customers (each exactly once) with any number of routes,
minimizing **total travel distance**.

CVRP is NP-hard: instances with a few dozen customers cannot be solved exactly
and require heuristics (nearest-neighbour, savings, 2-opt, large neighbourhood
search, metaheuristics, ...).

## Instances (data/instances/, data/instances_heldout/)

24 deterministically generated clustered instances (modelling city-like
customer distributions, coordinates 1..100, rounded Euclidean distances):

- **12 public instances** (data/instances/, `VRP-*`):

| Instance | Customers | Capacity | Instance | Customers | Capacity |
|----------|-----------|----------|----------|-----------|----------|
| VRP-19-2 | 19 | 270 | VRP-45-7 | 45 | 150 |
| VRP-21-3 | 21 | 165 | VRP-48-7 | 48 | 170 |
| VRP-22-4 | 22 | 130 | VRP-54-8 | 54 | 175 |
| VRP-32-5 | 32 | 160 | VRP-55-8 | 55 | 185 |
| VRP-37-6 | 37 | 145 | VRP-60-9 | 60 | 160 |
| VRP-45-6 | 45 | 190 | VRP-60-10 | 60 | 165 |

- **12 held-out instances** (data/instances_heldout/, `VHO-*`): scored at
  evaluation time alongside the public ones, doubling the evaluation set to 24.
  Their files stay on the host and are **not** copied into the evaluation
  sandbox, so you cannot read them during development — each path is handed to
  your solver only at scoring time. Hardcoding routes by instance name is
  rejected statically, and `CVRP_EVAL_GENERATE_SEED` can add fresh instances at
  evaluation time so the scored set is not predictable. Scoring on the
  held-out set measures whether the agent learned a *generalizable* solving
  method.

The file name is the instance name (e.g. `VRP-19-2.vrp`), in TSPLIB style
(`NODE_COORD_SECTION` / `DEMAND_SECTION` / `DEPOT_SECTION`, depot is node 1).
Instances are generated deterministically by `verification/generate_instances.py`
(seed 42; the per-instance `seed_key` is fixed to the original release
identifiers so the dataset stays byte-identical across releases).

## Input / output contract

### Candidate program `baseline/solver.py`

```python
# EVOLVE-BLOCK-START
def solve(instance):
    """Takes an instance dict, returns a list of routes list[list[int]].
    Each route is a visit sequence of customer ids (1..n, depot 0 excluded)."""
    ...
# EVOLVE-BLOCK-END
```

- `instance` fields:
  - `n`: number of customers (ids 1..n; depot is 0)
  - `capacity`: vehicle capacity
  - `demand`: `demand[0..n]`, `demand[0] == 0`
  - `distance`: `(n+1)×(n+1)` rounded-Euclidean distance matrix,
    `distance[0][c]` = depot-to-customer-c distance
- Output: `list[list[int]]`. Each route is a **customer-id sequence** (depot 0
  excluded), e.g. `[[3,1,5],[2,4]]` means two vehicles.
- Standalone run: `python baseline/solver.py <instance.vrp> <output.json>`
  (the fixed I/O part must not be modified).

### Validation rules

Each candidate output is checked:
1. Well-formed: `routes` is a list of lists of integers in 1..n;
2. **Full coverage**: the union of all routes is exactly {1..n}
   (no duplicates, none missing);
3. **Capacity**: `sum(demand[c]) <= capacity` per route.

Any violation → that instance is invalid (0 points) and the whole candidate
gets `valid=0`.

### Candidate integrity checks (preflight)

Before running, the evaluator statically rejects a candidate that:
- removes or reorders the `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END` markers,
  or modifies code outside the evolve block relative to the initial baseline;
- references the verification module, the reference solver, or
  `reference.json` (e.g. `import verification.ref_solver`);
- contains absolute filesystem paths;
- hardcodes per-instance routes by name (e.g. `"VRP-19-2": [...]`).

Violating candidates score 0 and are marked invalid. The candidate subprocess
also runs in an environment stripped of host benchmark paths, so it cannot
locate `reference.json` on the host; the evaluation sandbox contains only the
files the candidate needs (instances + evaluator glue), never the reference
solver or `reference.json`.

## Scoring

```
score_instance = min(100, 100 × reference_distance / candidate_distance)
combined_score = mean(score_instance)     # average over the 24 instances (12 public + 12 held-out)
valid          = all instances valid ? 1 : 0
```

- `reference_distance` comes from `data/reference.json`, precomputed by
  `verification/ref_solver.py`: a **deterministic** GRASP multi-start +
  2-opt + relocate/swap/2-opt* + LNS (greedy repair with tabu diversification)
  that keeps the best result over the fixed seed list `(123, 2024, 7)`, so
  regeneration is byte-identical on any machine. The reference is
  near-optimal (cross-checked against the archived best agent solver and an
  OR-Tools GLS solve).
- **100 = reference-quality solutions**; candidates shorter than the reference
  exceed 100 and are truncated to 100. Reaching 100 means the solution is
  close to the practical optimum of the instance.
- Optional score knob `CVRP_EVAL_SCORE_SCALE` (default 1.0):
  `score = min(100, scale × 100 × ref / cand)`. A scale < 1 tightens the 100
  bar (e.g. scale=2/3 requires the candidate to be no longer than 2/3 of the
  reference distance to score 100).
- Invalid / crashing / timing-out candidates: 0 on that instance and
  `valid=0` for the whole run.

## How to run

```bash
# Evaluate a candidate solver (inside the CVRP directory)
python verification/evaluator.py baseline/solver.py

# Evaluate on a subset of instances
python verification/evaluator.py baseline/solver.py --instances VRP-19-2 VRP-32-5

# Run the unit tests (evaluator / validator / candidate checks)
python verification/test_evaluator.py

# Unified-task adapter check (repo root, process mode)
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0

# Unified-task adapter check (repo root, docker isolation; requires building
# the image first: docker build -t cvrp-benchmark -f verification/docker/Dockerfile .)
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0 task.runtime.isolation_mode=docker task.runtime.docker_image=cvrp-benchmark
```

Environment variables: `CVRP_EVAL_TIMEOUT_S` (per-instance subprocess timeout,
default 60), `CVRP_EVAL_INSTANCES` (instance subset), `CVRP_EVAL_MAX_INSTANCES`
(instance cap), `CVRP_EVAL_SCORE_SCALE` (score knob, default 1.0).

## Reference scores (measured on this machine, against the current reference.json)

The current evaluation set is 24 instances (12 public + 12 held-out). The
agent scores below were measured on the **earlier 12-public-instance set**
(held-out instances were added later) and are kept for cross-framework
comparison; fresh runs on the full 24-instance set (ShinkaEvolve 98.65,
openevolve 98.00, AB-MCTS 99.26) show the learned solvers generalize to
unseen instances. See README "Experiments" for run records and multi-run
statistics.

| Solver | combined_score |
|--------|----------------|
| baseline (random-order cheapest insertion), 24 instances | **54.69** |
| reference (deterministic GRASP + LNS, scoring baseline) | 100 (near-optimal) |
| agent (openevolve, 5 iterations, best, 12-instance set) | 96.38 |
| agent (openevolve, 5 iterations, best, 24-instance set) | 98.00 |
| agent (ShinkaEvolve, 5 generations, best, 12-instance set) | 99.31 |
| agent (ShinkaEvolve, 5 generations, best, 24-instance set) | 98.65 |
| agent (AB-MCTS, 5 candidates, best, 12-instance set) | 98.70 |
| agent (AB-MCTS, 5 candidates, best, 24-instance set) | 99.26 |

## Optimisation hints (weak → strong)

1. **Random-order cheapest insertion** (baseline): insert customers one by
   one, in a random order, at their cheapest feasible position across all
   routes — a weak but standard randomized construction.
2. **Clarke-Wright savings**: merge routes by decreasing
   `d(0,i)+d(0,j)-d(i,j)` — a clear improvement.
3. **Intra-route 2-opt**: flip route segments to remove crossings — better.
4. **Cross-route local search**: relocate / swap / 2-opt*.
5. **Large neighbourhood search (LNS) / simulated annealing / genetic
   algorithms**: approach or beat the reference.

Every step is a verifiable score gain. **First guarantee validity (full
coverage + capacity), then optimize distance.**
