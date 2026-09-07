# Task 02 Specification: CVaR Stress-Controlled Allocation

## Background

You are allocating a long-only portfolio using scenario returns.
The PM requires a minimum expected return, while risk wants tail-loss control.
You therefore minimize CVaR subject to return and operational constraints.

## Input

`instance` dict fields:
- `scenario_returns`: `np.ndarray`, shape `(T, N)`
- `mu`: `np.ndarray`, shape `(N,)`, expected returns estimate
- `w_prev`: `np.ndarray`, shape `(N,)`
- `lower`: `np.ndarray`, shape `(N,)`
- `upper`: `np.ndarray`, shape `(N,)`
- `sector_ids`: `np.ndarray`, shape `(N,)`
- `sector_lower`: `dict[int, float]`
- `sector_upper`: `dict[int, float]`
- `beta`: `float` in `(0,1)` for CVaR confidence
- `target_return`: `float`
- `turnover_limit`: `float` (`||w - w_prev||_1` cap)

## Output

Return:
- `weights`: `np.ndarray` shape `(N,)`

## Objective and Constraints

Minimize CVaR of scenario loss:
- loss in scenario `t`: `L_t = -R_t^T w`
- `CVaR_beta = alpha + 1/((1-beta)T) * sum_t u_t`
- with `u_t >= L_t - alpha`, `u_t >= 0`

Subject to:
- `sum(w) == 1`
- `lower_i <= w_i <= upper_i`
- `mu^T w >= target_return`
- sector lower/upper constraints
- turnover cap via L1 distance to `w_prev`

## Expected Result

Good solutions should keep tail loss close to optimal while satisfying all constraints.

## Scoring

Per instance:
1. Look up the reference optimal CVaR `c_ref` (a precomputed constant; see below).
2. **Hard feasibility gate.** Every constraint is re-checked independently of the
   objective. If any residual exceeds its tolerance the instance scores `0`:

   | constraint | residual | tolerance |
   | --- | --- | --- |
   | budget | `abs(sum(w) - 1)` | `1e-6` |
   | per-asset bounds | `max(lower - w, w - upper)` | `1e-6` |
   | sector bounds | worst sector over/under-shoot | `1e-5` |
   | turnover | `norm1(w - w_prev) - turnover_limit` | `1e-4` |
   | return floor | `target_return - mu @ w` | `1e-8 + 1e-4 * target_return` |

   There is no partial credit and no `(1 - penalty)` multiplier: a portfolio that
   misses its mandated return or breaches an exposure limit is not deployable, so
   shaving CVaR by breaching a limit is worth nothing rather than costing a few
   points.
3. Compute candidate CVaR `c_cand` and normalize:
   - `c_anchor = max(CVaR(uniform), CVaR(w_prev))`
   - `norm = clip((c_anchor - c_cand) / (c_anchor - c_ref + 1e-12), 0, 1)`
4. Instance score: `100 * norm`.

Average over instances is the final score. `valid` is `1` only when every
instance produced a well-formed, feasible weight vector.

## How the candidate is run

`solve_instance(instance)` is called in a **separate process**. Only the weight
vector crosses back; the scorer recomputes CVaR and every constraint itself.
Nothing the candidate reports about its own score is read, and the scorer's
module globals are not reachable from the candidate.

## Theoretical Upper Bound

This is a convex LP/SOCP-equivalent formulation. The reference CVXPY optimum is the
practical theoretical upper bound under this benchmark (score 100).

## Implementation Notes

A non-library baseline can be built as:
- estimate each asset tail risk from worst scenarios,
- create risk-adjusted scores (`mu / tail_risk`),
- convert to initial weights,
- enforce turnover and exposures,
- greedily tilt to meet return target.

This gives a feasible heuristic even without a generic solver.

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
