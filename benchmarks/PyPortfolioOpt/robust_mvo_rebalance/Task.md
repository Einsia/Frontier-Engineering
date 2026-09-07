# Task 01 Specification: Robust MVO Rebalancing

## Background

You are implementing a portfolio rebalancer for an equity strategy.
The strategy outputs expected returns `mu` and covariance `Sigma`, but risk and operations
require additional controls:
- per-asset bounds,
- sector lower/upper bounds,
- style/factor exposure bounds,
- turnover limit from current holdings,
- L1 transaction penalty.

This is a constrained convex optimization problem.

## Input

The solver receives a Python `dict` named `instance`:

- `mu`: `np.ndarray`, shape `(N,)` expected returns.
- `cov`: `np.ndarray`, shape `(N, N)` PSD covariance matrix.
- `w_prev`: `np.ndarray`, shape `(N,)`, current portfolio weights.
- `lower`: `np.ndarray`, shape `(N,)`, lower bounds.
- `upper`: `np.ndarray`, shape `(N,)`, upper bounds.
- `sector_ids`: `np.ndarray`, shape `(N,)`, integer sector id per asset.
- `sector_lower`: `dict[int, float]` lower exposure by sector.
- `sector_upper`: `dict[int, float]` upper exposure by sector.
- `factor_loadings`: `np.ndarray`, shape `(N, K)`, asset exposures to K risk factors.
- `factor_lower`: `np.ndarray`, shape `(K,)`, lower bound for portfolio factor exposure.
- `factor_upper`: `np.ndarray`, shape `(K,)`, upper bound for portfolio factor exposure.
- `risk_aversion`: `float`.
- `transaction_penalty`: `float`.
- `turnover_limit`: `float`, L1 turnover cap.

## Output

Return a `dict` with:
- `weights`: `np.ndarray` shape `(N,)`.

Optional fields are ignored by evaluator.

## Objective and Constraints

Maximize:

`mu^T w - risk_aversion * w^T cov w - transaction_penalty * ||w - w_prev||_1`

Subject to:
- `sum(w) == 1`
- `lower_i <= w_i <= upper_i`
- sector constraints:
  - `sector_lower[s] <= sum_{i in sector s} w_i <= sector_upper[s]`
- factor exposure constraints:
  - `factor_lower[k] <= sum_i factor_loadings[i, k] * w_i <= factor_upper[k]`
- turnover:
  - `||w - w_prev||_1 <= turnover_limit`

## Expected Result

A high-quality solution should:
- be feasible up to numerical tolerance,
- achieve objective value close to the convex optimum.

## Scoring

For each test instance:
1. Look up the reference optimal objective `f_ref` (a precomputed constant; see below).
2. **Hard feasibility gate.** Every constraint is re-checked independently of the
   objective. If any residual exceeds its tolerance the instance scores `0`:

   | constraint | residual | tolerance |
   | --- | --- | --- |
   | budget | `abs(sum(w) - 1)` | `1e-6` |
   | per-asset bounds | `max(lower - w, w - upper)` | `1e-6` |
   | sector bounds | worst sector over/under-shoot | `1e-5` |
   | factor exposure | worst factor over/under-shoot | `1e-5` |
   | turnover | `norm1(w - w_prev) - turnover_limit` | `1e-4` |

   There is no partial credit and no `(1 - penalty)` multiplier: a portfolio that
   breaches a risk limit is not deployable, so overshooting a limit to buy
   objective is worth nothing rather than costing a few points.
3. Compute candidate objective `f_cand` and normalize against a naive anchor:
   - `f_anchor = min(f_uniform, f_prev_holdings)`
   - `norm = clip((f_cand - f_anchor) / (f_ref - f_anchor + 1e-12), 0, 1)`
4. Instance score: `100 * norm`.

Final score is the average over all instances. `valid` is `1` only when every
instance produced a well-formed, feasible weight vector.

## How the candidate is run

`solve_instance(instance)` is called in a **separate process**. Only the weight
vector crosses back; the scorer recomputes the objective and every constraint
itself. Nothing the candidate reports about its own score is read, and the
scorer's module globals are not reachable from the candidate.

## Theoretical Upper Bound

Because this is a convex problem, the reference solution (CVXPY global optimum)
is the practical theoretical upper bound under this formulation.
Its score is `100`.

## Implementation Notes

A practical non-library baseline can use:
- projected gradient ascent on a smoothed objective,
- iterative repair/projection for constraints:
  - clip to bounds,
  - enforce turnover by shrinking delta from `w_prev`,
  - enforce sector bounds by proportional redistribution,
  - renormalize to `sum(w)=1`.

This baseline is not globally optimal but should produce feasible solutions.

## Baseline Implementation (this repo)

- File: `baseline/init.py`
- Method class: projected first-order heuristic (no external optimizer)
- Core idea:
  - smooth the L1 term and take gradient steps on the objective,
  - repeatedly repair weights to satisfy bounds, sector limits, turnover, and budget sum.
- Characteristic:
  - fast and dependency-light,
  - does not explicitly project onto factor-exposure constraints,
  - does not guarantee global optimality.

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
