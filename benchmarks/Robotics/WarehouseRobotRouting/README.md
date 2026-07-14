# Warehouse Robot Routing

This benchmark asks a solver to assign pickup-and-delivery orders to warehouse robots and produce complete discrete-time paths without collisions or capacity violations.

## Objective

For a valid solution, the verifier independently counts every edge traversal by every robot:

- `D`: verified total move distance; waiting does not contribute.
- Raw metric: `C = D + 1`, minimized.
- Baseline-normalized score: `log2(C_baseline / C)`.
- Dataset score: arithmetic mean across instances.
- Invalid solutions receive `-1e18`.

A baseline-equivalent solution scores `0`; lower distance gives a positive score.

## Instances

`generate_instances(seed)` deterministically returns four instances. Public seeds are `101`, `103`, `107`, `109`, and `113`. Evaluation seeds remain reserved by the benchmark configuration.

Each instance contains an undirected warehouse graph, robot start nodes and capacities, weighted pickup-and-delivery orders, and a finite horizon `H`. Generated layouts use aisle-like grids with narrow cross-aisles and private robot parking nodes.

## Solver contract

The candidate entry point is `solve(instance)` in `scripts/init.py`. It returns one record for every robot. Each path must contain exactly `H + 1` node identifiers, representing times `0` through `H` inclusive. Actions refer to the robot position at their stated time.

The supplied candidate is a deterministic feasible baseline. It greedily inserts orders into per-robot service sequences, routes one order at a time, reserves non-overlapping robot execution windows, and pads all paths to the horizon.

`verification/problem.py` provides deterministic instance generation, random and baseline solvers, a stronger reference solver, strict validation, and evaluation. The reference uses subset dynamic programming to optimize assignment and macro-order sequencing, and safely avoids the baseline's unnecessary final return for the last active robot. Benchgen's smoke and calibration gates independently check baseline feasibility, determinism, and reference improvement.

## Verification

The verifier does not trust declared costs, loads, or feasibility. It checks the complete output structure, identifiers, starts, graph moves, vertex conflicts, opposite-direction edge swaps, action locations, action uniqueness and ordering, robot capacities, and completion of every order. It then recomputes distance from the submitted paths.

## Running Modes

Docker isolation is the publish and evaluation default. Run the normal Benchgen command without `--local` for publish-quality results. The immutable runtime image is declared in `benchmark.yaml`; networking is disabled.

Trusted local development may append `--local` to the same Benchgen command. Local mode executes candidate code directly on the host and must only be used with code you trust. Do not publish results produced only in local mode.

## Scope and Reality Gap

The benchmark models deterministic unit-time graph movement, vertex conflicts, head-on edge conflicts, and payload changes. It does not model continuous dynamics, acceleration, localization error, temporary obstacles, charging, communication latency, or hardware failure. Deployment requires motion control, safety margins, and online replanning beyond this benchmark.

Reducing valid route distance can lower energy use and equipment wear while improving fulfillment throughput. The benchmark cites Ma et al., *Lifelong Multi-Agent Path Finding for Online Pickup and Delivery Tasks* (AAMAS 2017, arXiv:1705.10868), as its public MAPD evidence source.

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## Evaluation Contract

The verifier recomputes `verified_total_move_distance_plus_one` and candidates must minimize it.
Each valid case is scored by `log2` improvement over the baseline and the final score is the
mean across cases. Invalid solutions receive `-1e18`.

Local execution is only for reviewed code:

```bash
python verification/evaluator.py scripts/init.py --local
```

Publish evaluation requires Docker and the pinned runtime image:

```bash
docker pull python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
python verification/evaluator.py scripts/init.py
```
<!-- BENCHGEN-PUBLIC-CONTRACT-END -->
