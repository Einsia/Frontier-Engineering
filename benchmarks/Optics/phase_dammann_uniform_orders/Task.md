# Phase DOE P3 Contract: Dammann Uniform Orders

## Background
This is a **parameter optimization** task.
You optimize a 1D vector `transitions` (binary phase switching positions in one grating period), and evaluate a simulator output.

Think of it as:
- decision variable: `transitions` (continuous vector)
- simulator: `diffractio` propagation pipeline
- objective: make selected diffraction orders both uniform and efficient

## What You Need To Do
Improve how baseline chooses transition positions.

Primary optimization target:
- `solve(problem)` in `baseline/init.py`

`main()` writes the returned vector to `submission.json`. The verifier builds the
optical field, propagates it and evaluates the order metrics.

## Editable Boundary
- Editable: `baseline/init.py`
- Read-only (write-locked and fingerprinted during evaluation): `verification/validate.py`, `verification/problem.py`, `verification/metrics.py`, `frontier_eval/`

## Scoring Contract
`baseline/init.py` is **never imported** by the verifier. It is executed as a
standalone program in its own subprocess, inside a throwaway working directory that
already holds the scorer-authored problem definition:

- `problem.json` -- the config (`cfg`) plus a `decision_variable` block stating exactly what to return
- `problem.npz` -- `x_period`

Your program must write `submission.json` into its current directory and exit 0:

```json
{"transitions": [t0, t1, ..., t13]}   // micrometres
```

Constraints the verifier enforces on `transitions`:
- exactly `cfg["num_transitions"]` (14) numbers
- **strictly increasing**
- every entry finite and inside `[-period_size/2, +period_size/2]`

**Return the decision variable and nothing else.** Any other key -- `metrics`,
`score`, `score_pct`, `cv_orders`, ... -- is dropped before scoring and merely recorded
under `contract.ignored_submission_keys` in the metrics file. The problem definition,
the forward model and every metric live in `verification/problem.py` and
`verification/metrics.py`: the verifier rebuilds the problem, runs the forward model on
your decision variable, and computes all metrics. The oracle uses the same scoring
functions.

A rejected submission (wrong shape/length, non-finite or out-of-range values, non-zero
exit code, timeout, or no `submission.json`) scores as invalid.

## Baseline Implementation (current)
Baseline picks naive evenly-spaced transitions inside fixed margins. Steps 1-5 below are
the verifier's forward model (`verification/metrics.py`), not yours:
1. build one-period binary phase mask
2. repeat period to build full grating
3. multiply lens phase
4. propagate with Rayleigh-Sommerfeld (`RS`)
5. integrate order-window energies

## Oracle Implementation
Verifier evaluates two stronger references and picks higher score:
1. literature transition table (from diffractio Dammann example)
2. SciPy differential evolution (`scipy.optimize.differential_evolution`)

Oracle is `best_of_literature_and_scipy_de`.

## Metrics and Score (Higher Is Better)
Raw metrics:
- `cv_orders` (lower better)
- `efficiency` (higher better)
- `min_to_max` (higher better)

Score:
- `uniform_score = clip(1 - cv_orders / 0.9, 0, 1)`
- `efficiency_score = clip((efficiency - 0.003) / (0.18 - 0.003), 0, 1)`
- `balance_score = clip((min_to_max - 0.15) / (0.90 - 0.15), 0, 1)`
- `score_pct = 100 * (0.60*uniform_score + 0.30*efficiency_score + 0.10*balance_score)`

Range: `0 ~ 100`, higher is better.

## Valid Criteria
- `cv_orders <= 0.8`
- `efficiency >= 0.003`
- `min_to_max >= 0.15`

## Practical Evolution Directions
- constrained continuous optimization over transitions
- symmetry-aware parameterization
- objective balancing between uniformity and efficiency
- spacing constraints for manufacturability

