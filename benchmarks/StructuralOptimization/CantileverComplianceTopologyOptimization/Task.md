# Cantilever Compliance Topology Optimization Task

## Problem

Update densities inside a frozen cantilever pyMOTO topology-optimization loop and minimize final compliance.

This benchmark stands in for lightweight bracket and support design. With a fixed material budget, the objective is to make the cantilever as stiff as possible.

From a CS point of view, this is optimizer design inside a frozen FEM/SIMP loop rather than one-shot prediction.

## What Is Frozen

- The pyMOTO finite-element model, geometry, loads, passive masks, and SIMP settings in `runtime/problem.py`.
- The material budget, minimum density, move limit, and 30-step optimization horizon.
- The compliance objective and the feasibility validator for each intermediate density update.

## Submission Contract

Submit one Python file that defines:

```python
def update_density(density, sensitivity, state):
    ...
```

`density` is the current density vector, `sensitivity` is the current compliance sensitivity, and `state` includes keys such as `iteration`, `domain_shape`, `volume_fraction`, `target_density_sum`, `minimum_density`, `move_limit`, `current_compliance`, `history`, `passive_solid_mask`, and `passive_void_mask`.

Return the next feasible density vector, or a dict with key `density`. If you want a projection helper, you may import `project_density` from `runtime.problem`.

## Evaluation

1. Build the frozen pyMOTO model from `runtime/problem.py`.
2. Run the fixed 30-iteration optimization loop with your `update_density(...)` callback.
3. Validate every intermediate density update against bounds, move limits, masks, and volume conservation.
4. Report final candidate compliance and compare it with the OC-style baseline for context.

## Metrics

- `combined_score`: `-candidate_compliance`
- `valid`: `1.0` only if every update is finite and feasible
- `candidate_compliance`
- `baseline_compliance`
- `final_volume_fraction`
- `volume_fraction_error`

## Invalid Submissions

- `update_density(...)` is missing or crashes
- Any proposed density contains non-finite values
- Any update violates bounds, move limits, passive masks, or the target density sum
- The pyMOTO solve fails during evaluation

<!-- AI_GENERATED -->
