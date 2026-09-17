# LA16 Dispatching Rule Optimization Task

## Problem

Design a greedy dispatching rule for the canonical LA16 Lawrence 10x10 job shop and minimize makespan.

This benchmark is the same policy-design problem as FT10, but on the canonical LA16 bottleneck structure. Small local scoring changes can still produce large throughput differences.

You are again writing a local priority function inside a fixed scheduler rather than constructing the schedule yourself.

## What Is Frozen

- The canonical `la16` instance and the known optimum `945`.
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

1. Load the canonical `la16` instance from `runtime/problem.py`.
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
