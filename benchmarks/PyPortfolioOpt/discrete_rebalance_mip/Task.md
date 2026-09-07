# Task 03 Specification: Discrete Rebalance MIP

## Background

You have target portfolio weights from a model, but execution must use integer lots.
You also need to control transaction fees and turnover notional.

This is a mixed-integer linear optimization problem.

## Input

`instance` dict fields:
- `prices`: `np.ndarray`, shape `(N,)`
- `lot_sizes`: `np.ndarray`, shape `(N,)`, positive integers
- `current_lots`: `np.ndarray`, shape `(N,)`, current integer lots
- `target_weights`: `np.ndarray`, shape `(N,)`, sum close to 1
- `portfolio_value`: `float`, total budget for final holdings + fees
- `fee_rate`: `float`, proportional fee on traded notional
- `turnover_limit_value`: `float`, max traded notional
- `max_lots`: `np.ndarray`, shape `(N,)`, upper bound for each lot variable

Define unit notional per lot: `unit_i = prices_i * lot_sizes_i`.

## Output

Return:
- `lots`: `np.ndarray`, shape `(N,)`, integer final lots

Optional fields are ignored.

## Objective and Constraints

Minimize:

`sum_i |unit_i * lots_i - target_weights_i * portfolio_value| + fee_rate * traded_notional`

where:

`traded_notional = sum_i unit_i * |lots_i - current_lots_i|`

Subject to:
- `0 <= lots_i <= max_lots_i`, integer
- `traded_notional <= turnover_limit_value`
- `sum_i unit_i * lots_i + fee_rate * traded_notional <= portfolio_value`

## Expected Result

A strong solution has low target-tracking error with feasible execution constraints.

## Scoring

Per instance:
1. Look up the reference integer optimum `obj_ref` (a precomputed constant; see below).
2. **Hard feasibility gate.** Every constraint is re-checked independently of the
   objective. If any residual exceeds its tolerance the instance scores `0`:

   | constraint | residual | tolerance |
   | --- | --- | --- |
   | integrality | `abs(lots - round(lots))` | `1e-6` |
   | lot bounds | `max(-lots, lots - max_lots)` | `1e-6` |
   | turnover notional | `traded_notional - turnover_limit_value` | `1e-6 + 1e-9 * limit` |
   | budget | `spend - portfolio_value` | `1e-6 + 1e-9 * portfolio_value` |

   There is no partial credit and no `(1 - penalty)` multiplier. This matters most
   here: an order list that ignores the turnover cap reaches a *lower* objective
   than the true integer optimum, so under a soft penalty an unexecutable basket
   was still worth points.
3. Compute candidate objective `obj_cand` and normalize against no-trade:
   - `obj_anchor = objective(current_lots)`
   - `norm = clip((obj_anchor - obj_cand) / (obj_anchor - obj_ref + 1e-12), 0, 1)`
4. Instance score: `100 * norm`.

Average score over instances is the final score. `valid` is `1` only when every
instance produced a well-formed, feasible lot vector.

## How the candidate is run

`solve_instance(instance)` is called in a **separate process**. Only the lot
vector crosses back; the scorer recomputes the objective and every constraint
itself. Nothing the candidate reports about its own score is read, and the
scorer's module globals are not reachable from the candidate.

## Theoretical Bound

- Practical benchmark upper bound: reference integer optimum (`100` score).
- Additional theoretical comparator: LP relaxation lower bound (continuous lots),
  reported by evaluator for integrality-gap analysis.

## Implementation Notes

Without calling external optimizers, a solid baseline can use:
- rounded initialization from target notional,
- feasibility repair loops for budget/turnover,
- local search over +/- 1 lot moves,
- greedy fill of underweight assets when constraints allow.

This is typical for production heuristics when exact MIP is too slow.

## Reference Implementation (this repo)

- File: `verification/reference.py`
- Method class: exact convex/integer optimization with CVXPY
- Role: produced the frozen reference objective table used for normalization.

> **Not available to the candidate.** `verification/reference.py` is maintainer-only.
> It is excluded from `agent_files.txt` and from the `copy_files.txt` allowlist, and
> the evaluator never imports or executes it: the reference values it produced are
> frozen into `verification/evaluate.py` as a constant table (the evaluation seeds
> are fixed, so they are fully precomputable). Regenerate with
> `python verification/evaluate.py --regenerate-reference-table`.
