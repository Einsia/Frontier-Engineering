# Phase DOE P1 Contract: Hard Weighted Multi-Spot

## Background
You can view this task as a **2D optimization problem**:
- Input: a phase map `phase[y, x]`
- Black-box forward model: `phase -> far-field intensity`
- Goal: make many target spots receive desired relative energy

In optics terms, this is phase-only Fourier holography. In ML/optimization terms, this is a non-convex objective over a 2D array.

## What You Need To Do
Improve the baseline in `baseline/init.py` so that the generated phase map achieves better weighted spot distribution.

Recommended modification point:
- `solve(problem)` in `baseline/init.py`

You can add helper functions in the same file; the only fixed contract is the
`submission.json` schema below.

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
your decision variable itself, and recomputes all metrics. Nothing you report can move
the score, and the oracle is graded with the identical functions.

A rejected submission (wrong shape/length, non-finite or out-of-range values, non-zero
exit code, timeout, or no `submission.json`) scores as invalid.

## Baseline Implementation (current)
Baseline is intentionally simple:
1. For each target spot, create one plane-wave term in complex field
2. Weighted coherent sum over all spots
3. Use angle of summed field as phase map

This is fast and deterministic but not iterative, so dense non-uniform targets are hard.

## Oracle Implementation
Oracle in verifier uses `slmsuite` weighted Gerchberg-Saxton:
- `Hologram.optimize(method="WGS-Kim")`
- Iteratively updates hologram to better match target energy distribution

So oracle is a stronger iterative solver; baseline is non-iterative.

## Metrics and Score (Higher Is Better)
Verifier computes:
- `ratio_mae`: mean absolute error between achieved spot ratios and target ratios (lower better)
- `cv_spots`: coefficient of variation of per-spot energy (lower better)
- `efficiency`: fraction of total energy captured by target windows (higher better)
- `min_peak_ratio`: weakest target peak / strongest target peak (higher better)

Then:
- `ratio_score = clip(1 - ratio_mae / 0.07, 0, 1)`
- `uniform_score = 1 / (1 + (cv_spots / 0.85)^2)`
- `efficiency_score = clip((efficiency - 0.15) / (0.80 - 0.15), 0, 1)`
- `peak_score = clip((min_peak_ratio - 0.003) / (0.20 - 0.003), 0, 1)`
- `score = 0.25*ratio_score + 0.45*uniform_score + 0.20*efficiency_score + 0.10*peak_score`
- `score_pct = 100 * score` (compatibility field)

Range: `0 ~ 1` (higher is better).

## Valid Criteria
Baseline is valid if all true:
- `score >= 0.20`
- `efficiency >= 0.45`
- `min_peak_ratio > 0`

## Expected Optimization Space
Typical improvements that work:
- iterative phase retrieval (GS/WGS variants)
- per-spot feedback correction
- regularization or damping for stability
- better initialization than direct superposition
