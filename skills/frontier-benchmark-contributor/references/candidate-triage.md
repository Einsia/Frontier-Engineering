# Candidate Triage For The Current Frontier-Engineering Expansion

Use this file when the user asks which ideas from the current candidate pool should be implemented first.

## Tier A: Fastest To Land

These are the best first contributions because they are small, deterministic, and easy to score.

1. Stockpyl single-node EOQ extensions with MOQ and supplier discount variants.
2. Stockpyl stochastic demand with service-level constrained `(s, Q)` or `(R, Q)` policies.
3. Job shop scheduling with FT10 or LA16 using an existing solver as baseline and a heuristic surface for the agent.
4. PyPortfolioOpt static Markowitz portfolio optimization with fixed historical return matrices.
5. Simplified ship weather routing on a pre-generated 2D grid with offline wind/current fields.
6. Simplified water network MILP with a small hand-written network and a CBC or HiGHS baseline.

Why these are attractive:

1. They have narrow interfaces.
2. They admit clear baseline calls.
3. They can use synthetic or fixed local data.
4. They can expose interpretable metrics such as cost, makespan, Sharpe ratio, or route cost.

## Tier B: Viable After Moderate Simplification

These can work, but they need extra care around dependencies or benchmark scope.

1. PyPSA intraday operation with storage on a very small network.
2. EV2Gym simplified charging plus grid proxy.
3. pyMOTO topology optimization with fixed meshes and limited iteration budgets.
4. Motion planning from `caelan/motion-planners` for 2D or small 3D maps.
5. MESMO multi-energy scheduling only if the environment can be pinned and the instance is tiny.

Main risk:

The library stack or runtime may be heavier than the eventual benchmark warrants.

## Tier C: Defer Or Simplify Aggressively

Avoid these for the first batch unless the user explicitly wants a heavy benchmark and accepts extra engineering work.

1. CARLA-derived driving behavior planning.
2. SimRLFab RL scheduling with training loops.
3. OpenFF force-field fitting or MD performance tuning.
4. Sequoya multi-sequence alignment on real datasets.
5. DawnDesignTool aircraft multidisciplinary design.
6. Optiland optical system design.
7. Additive manufacturing differentiable simulation.
8. Data-center MARL cooling and scheduling.

Typical reasons to defer:

1. Dependency stacks are large or fragile.
2. Runtime is hard to bound.
3. Reproducibility is harder to guarantee.
4. Benchmark setup can dominate the actual task definition.

## Practical Selection Rule

When the user wants to contribute a batch:

1. Pick one Tier A task that is optimization-heavy but easy to score.
2. Pick one Tier A or B task from a different domain for diversity.
3. Delay Tier C until the repo has enough lighter tasks landed successfully.

If uncertain between two tasks, choose the one that can be implemented with `task=unified`.
