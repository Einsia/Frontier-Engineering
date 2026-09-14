# Phase DOE P4 Contract: Large-Scale Weighted Spot Array

## Background
This task is dense multi-target allocation:
- decision variable: phase map `(N, N)`
- forward model: Fourier propagation
- objective: satisfy weighted energy allocation over many spots (8x8)

Compared with Task01, this one has larger target count and broader distribution.

## What You Need To Do
Improve baseline phase generation so weighted spot-array quality increases.

Main function to optimize:
- `solve(problem)` in `baseline/init.py`

## Editable Boundary
- Editable: `baseline/init.py`
- Read-only (write-locked and fingerprinted during evaluation): `verification/validate.py`, `verification/problem.py`, `verification/metrics.py`, `frontier_eval/`

## Scoring Contract
`baseline/init.py` is **never imported** by the verifier. It is executed as a
standalone program in its own subprocess, inside a throwaway working directory that
already holds the scorer-authored problem definition:

- `problem.json` -- the config (`cfg`) plus a `decision_variable` block stating exactly what to return
- `problem.npz` -- `x`, `y`, `spots`, `weights`, `aperture_amp`

Your program must write `submission.json` into its current directory and exit 0:

```json
{"phase": [[...128 floats...], ...]}   // 128 rows, radians
```

Constraints the verifier enforces on `phase`:
- shape exactly `(128, 128)`
- every entry finite and `|phase| <= 1e4`

**Return the decision variable and nothing else.** Any other key -- `metrics`,
`score`, `score_pct`, `cv_orders`, ... -- is dropped before scoring and merely recorded
under `contract.ignored_submission_keys` in the metrics file. The problem definition,
the forward model and every metric live in `verification/problem.py` and
`verification/metrics.py`: the verifier rebuilds the problem, runs the forward model on
your decision variable, and computes all metrics. The oracle uses the same scoring
functions.

A rejected submission (wrong shape/length, non-finite or out-of-range values, non-zero
exit code, timeout, or no `submission.json`) scores as invalid.

## Baseline Implementation
Baseline currently uses direct non-iterative weighted superposition of plane-wave terms, then takes phase.

## Oracle Implementation
Verifier oracle uses iterative `slmsuite` WGS:
- `Hologram.optimize(method="WGS-Kim")`

## Metrics and Score (Higher Is Better)
Raw metrics:
- `ratio_mae`
- `cv_spots`
- `efficiency`

Score formula:
- `ratio_score = clip(1 - ratio_mae / 0.03, 0, 1)`
- `uniform_score = clip(1 - cv_spots / 1.40, 0, 1)`
- `efficiency_score = clip((efficiency - 0.40) / (0.90 - 0.40), 0, 1)`
- `score_pct = 100 * (0.45*ratio_score + 0.35*uniform_score + 0.20*efficiency_score)`

Range: `0 ~ 100`, higher is better.

## Valid Criteria
- `score_pct >= 20`
- `ratio_mae <= 0.03`
- `cv_spots <= 1.40`
- `efficiency >= 0.50`

## Practical Evolution Directions
- iterative weighted correction (instead of one-shot phase)
- local phase refinement / block updates
- adaptive balancing between ratio and efficiency

