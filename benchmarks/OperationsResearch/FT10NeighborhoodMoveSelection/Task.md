# FT10 Neighborhood Move Selection Task

## Problem

Rank adjacent-swap moves for a frozen local-search shell on the canonical FT10 job shop and minimize makespan.

This benchmark models schedule refinement under a limited search budget. The scheduler already has a feasible incumbent; what matters is which neighboring move it tries first.

You are controlling move ranking inside a fixed local-search loop rather than searching the schedule space end to end yourself.

## What Is Frozen

- The canonical `ft10` instance and the known optimum `930`.
- The baseline SPT dispatch schedule used as the incumbent.
- The adjacent-swap move generator and first-improving acceptance rule in `runtime/problem.py`.

## Submission Contract

Submit one Python file that defines:

```python
MAX_ITERATIONS = 50


def score_move(move, state):
    ...
```

Define `score_move(move, state)` and return any finite scalar; larger scores are tried first. You may also set `MAX_ITERATIONS` to any positive integer if you want to change the search budget.

## Evaluation

1. Load the canonical `ft10` instance from `runtime/problem.py`.
2. Start from the frozen baseline dispatch schedule.
3. Repeatedly generate adjacent machine-order swap moves, rank them by `score_move(...)`, and apply the first improving move.
4. Stop when no improving move exists or `MAX_ITERATIONS` is reached, then report candidate makespan and diagnostics.

## Metrics

- `combined_score`: `-candidate_makespan`
- `valid`: `1.0` only if a complete feasible schedule is produced
- `candidate_makespan`
- `baseline_makespan`
- `relative_gap_to_optimum`

## Invalid Submissions

- `score_move(...)` is missing or crashes
- The returned move score is non-finite
- `MAX_ITERATIONS` is invalid or evaluation fails before a valid schedule is built
- The induced schedule becomes infeasible

<!-- AI_GENERATED -->
