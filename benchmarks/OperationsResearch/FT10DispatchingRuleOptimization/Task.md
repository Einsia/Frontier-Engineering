# FT10 Dispatching Rule Optimization Task

## Problem

Design a greedy dispatching rule for the canonical FT10 Fisher-Thompson 10x10 job shop and minimize makespan.

This benchmark stands in for online shop-floor dispatching, where lightweight priority rules are still used because they are easy to deploy and can materially change throughput and overtime.

You are not returning a full schedule. You are writing the priority function inside a frozen scheduler, so the task is policy design under a fixed simulator.

## What Is Frozen

- The canonical `ft10` instance and the known optimum `930`.
- The schedule builder, feasibility logic, and tie-handling protocol in `runtime/problem.py`.
- The rule that only operations with the earliest feasible start time are compared by your score.

## Submission Contract

Submit one Python file that defines:

```python
def score_operation(operation, state):
    ...
```

Return any finite scalar priority. Among operations tied on earliest feasible start time, larger scores are scheduled first.

## Evaluation

1. Load the canonical `ft10` instance from `runtime/problem.py`.
2. Start from an empty schedule and repeatedly collect the next unscheduled operation from each job.
3. Among operations tied on earliest feasible start time, pick the one with the highest `score_operation(...)`.
4. Build a complete schedule, compute candidate makespan, and report the baseline and relative gap to the optimum.

## Metrics

- `combined_score`: `-candidate_makespan`
- `valid`: `1.0` only if a complete feasible schedule is produced
- `candidate_makespan`
- `baseline_makespan`
- `relative_gap_to_optimum`

## Invalid Submissions

- `score_operation(...)` is missing or crashes
- The returned priority is non-finite
- The induced schedule is infeasible or incomplete
- Evaluation fails before a valid makespan is produced

<!-- AI_GENERATED -->
