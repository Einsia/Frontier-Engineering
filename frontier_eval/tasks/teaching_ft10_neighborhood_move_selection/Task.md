# FT10 Neighborhood Move Selection Task

## Problem

You are given the canonical FT10 job-shop instance and a frozen local-search shell.
Your job is to rank adjacent machine-order swaps so that the search trajectory reaches a smaller makespan.

This is not a full schedule-construction problem.
The evaluator already knows how to build the incumbent schedule, generate the neighborhood, apply swaps, and stop the search.
Your code only supplies a move-scoring policy.

## Background

Job-shop scheduling is a manufacturing optimization problem:
each job has to visit a fixed sequence of machines, and each machine can process only one operation at a time.
The objective is usually to minimize the final completion time, also called the makespan.

The FT10 instance is a classic 10-job, 10-machine benchmark.
It is hard because local machine decisions interact globally: a swap that looks harmless on one machine can delay a downstream bottleneck and increase the final makespan.

The teaching idea here is to separate the solver shell from the policy.
You can think of this as learning a ranking function for a combinatorial local search engine.

## What Is Frozen

- The FT10 instance `ft10`.
- The incumbent schedule used to start local search.
- The adjacent-swap neighborhood.
- The acceptance rule: only improving moves are applied.
- The theoretical optimum `930`, which is known for this instance.

## Input and Output

Your candidate file should define:

```python
def score_move(move, state):
    ...

MAX_ITERATIONS = 50
```

`score_move(move, state)` receives:

- `move`: a dictionary describing one adjacent swap
- `state`: a dictionary describing the current local-search iteration

The move dictionary contains:

- `machine_id`: the machine whose sequence is being modified
- `machine_position`: the index of the left element in the adjacent pair
- `op_a` and `op_b`: the two neighboring operations being considered for swap
- `delta_duration`: a cheap feature derived from the two operation durations
- `current_makespan`: the current schedule makespan

Each operation record inside `op_a` and `op_b` contains:

- `job_id`
- `op_index`
- `duration`
- `start`
- `end`

The state dictionary contains:

- `iteration`
- `current_makespan`

Return any finite scalar score.
Larger scores are tried first.
If you provide `MAX_ITERATIONS`, it must be a positive integer.

## Expected Result

A good submission should produce a feasible schedule with a smaller makespan than the baseline.
The best possible makespan for this instance is `930`.

You should expect the evaluator to run a local search loop like this:

1. Start from the baseline incumbent schedule.
2. Generate all adjacent machine-order swaps.
3. Rank them using `score_move(move, state)`.
4. Apply the first improving move in that ranked order.
5. Stop when there is no improving move or the iteration limit is reached.

That means a good score function should do more than prefer obviously short operations.
It should prefer swaps that are likely to unlock a better downstream machine order and reduce the critical path.

## How To Start Implementing

If you have a CS background, a practical implementation recipe is:

1. Treat `start` and `end` as a proxy for slack.
   Swaps involving operations that already sit near the schedule tail usually matter more.
2. Use `remaining_job_work` indirectly through the operation indices.
   Delaying an operation from a still-long job often hurts more than delaying the end of a short job.
3. Look for bottlenecks at the machine level.
   A swap near the end of a busy machine sequence can change the global makespan even if the two durations are similar.
4. Think in terms of the critical path.
   The makespan is determined by one or more tight precedence chains; the best swaps are usually the ones that shorten or reroute those chains.

In code, that usually means combining several weak signals into one score rather than relying on only `delta_duration`.

## Scoring

This is a minimization task, so lower makespans are better.
We report a normalized score on a 0 to 100 scale:

```text
normalized_score = 100 * clip((baseline_makespan - candidate_makespan) / (baseline_makespan - 930), 0, 1)
```

Interpretation:

- `0` means the candidate is no better than the baseline
- `100` means the candidate reaches the known optimum `930`
- invalid or infeasible submissions receive `0`

We also report:

- `candidate_makespan`
- `baseline_makespan`
- `reference_makespan`
- `theoretical_optimum_makespan`
- `gap_to_optimum`

## Why This Is Hard

The obvious greedy idea is to always move shorter operations earlier.
That helps sometimes, but it ignores the fact that the schedule is constrained by machine conflicts and job precedence.

The real difficulty is that a swap can change the critical path in a non-local way.
You are trying to improve a global objective using only a local neighborhood signal.
That is the central lesson of this benchmark.

## Failure Cases

The submission is invalid if:

- `score_move` is missing
- the returned score is non-finite
- `MAX_ITERATIONS` is invalid
- the induced schedule is incomplete or infeasible
- the evaluator cannot import or run the candidate file

<!-- AI_GENERATED -->
