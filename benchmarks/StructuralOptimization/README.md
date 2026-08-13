# Structural Optimization

This domain covers structural engineering optimization problems, including tasks derived from the **International Student Competition in Structural Optimization (ISCSO)**, organized by [Bright Optimizer](http://www.brightoptimizer.com/), and published laminate and topology benchmarks.

Structural optimization is a core discipline in civil, aerospace, and mechanical engineering, aiming to find the optimal design of load-bearing structures that minimizes material usage (weight) while satisfying safety constraints (stress and displacement limits).

## Tasks

| Task | Description | Dimension | Type |
| :--- | :--- | :---: | :--- |
| `ISCSO2015` | 45-bar 2D truss size + shape optimization | 54 | Continuous, constrained, multi-load-case |
| `ISCSO2023` | 284-member 3D truss sizing optimization | 284 | Continuous, constrained, multi-load-case |
| `TopologyOptimization` | MBB beam 2D topology optimization (SIMP) | 1200 | Continuous, volume-constrained, compliance minimization |
| `PyMOTOSIMPCompliance` | pyMOTO-style SIMP compliance minimization for 2D beam topology design | 4800 | Continuous, volume-constrained, compliance minimization |
| `CompositeLaminateStacking` | Balanced, symmetric 48-ply laminate design across plate geometries and load ratios | 120 | Discrete, multi-case, buckling + failure constrained |

## Why These Problems Are Suitable for Frontier-Engineering

| Feature | ISCSO 2015 | ISCSO 2023 | Composite laminate |
| :--- | :--- | :--- | :--- |
| High-dimensional design variables | Medium (54-D) | High (284-D) | High (120 integer variables) |
| Real physical model | FEM | FEM | Classical laminate theory + Ritz buckling |
| Deterministic evaluation | Yes | Yes | Yes |
| Multi-load-case constraints | Yes (2 cases) | Yes (3 cases) | Yes (10 cases) |
| Non-convex feasible region | Yes | Yes | Yes |
| Industrial relevance | Yes | Yes | Yes |

These benchmarks serve as:

- Black-box constrained optimization benchmarks
- Agent + FEM simulation interaction benchmarks
- Automated algorithm design benchmarks
- LLM + numerical simulation benchmarks

## Data and Runtime

The required reference data for these tasks is committed under each task's `references/` directory; no separate asset bundle is required. For unified runs, use the `frontier-v1-main` runtime environment, for example:

```bash
python -m frontier_eval task=unified task.benchmark=StructuralOptimization/ISCSO2015 task.runtime.env_name=frontier-v1-main algorithm.iterations=0
```
