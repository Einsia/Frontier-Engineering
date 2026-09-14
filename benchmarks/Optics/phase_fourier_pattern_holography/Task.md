# Phase DOE P2 Contract: Hard Fourier Pattern Holography

## Background
This task is image reconstruction under constraints:
- Decision variable: phase map `phase[y, x]`
- Forward model: FFT-based propagation to intensity image
- Objective: match a sparse high-contrast target while keeping dark zones dark

Equivalent CS view: constrained inverse problem / non-convex optimization on a 2D field.

## What You Need To Do
Improve `baseline/init.py` so the reconstructed intensity image better fits target structure and suppresses leakage in designated dark regions.

Primary function to optimize:
- `solve(problem)` in `baseline/init.py`

## Editable Boundary
- Editable: `baseline/init.py`
- Read-only (write-locked and fingerprinted during evaluation): `verification/validate.py`, `verification/problem.py`, `verification/metrics.py`, `frontier_eval/`

## Scoring Contract
`baseline/init.py` is **never imported** by the verifier. It is executed as a
standalone program in its own subprocess, inside a throwaway working directory that
already holds the scorer-authored problem definition:

- `problem.json` -- the config (`cfg`) plus a `decision_variable` block stating exactly what to return
- `problem.npz` -- `x`, `y`, `aperture_amp`, `target_amp`

Your program must write `submission.json` into its current directory and exit 0:

```json
{"phase": [[...128 floats...], ...]}   // 128 rows, radians
```

Constraints the verifier enforces on `phase`:
- shape exactly `(128, 128)`
- every entry finite and `|phase| <= 1e4`

`target_amp` is authored by the scorer and shipped to you read-only. It is the
target you are graded against; you cannot substitute your own.

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
Baseline is one-shot and non-iterative:
1. attach random phase to target amplitude
2. inverse FFT once
3. use resulting phase as hologram

Fast but weak for difficult sparse/high-contrast structures.

## Oracle Implementation
Oracle uses iterative weighted GS in `slmsuite`:
- `Hologram.optimize(method="WGS-Kim")`
- iterative amplitude/phase correction

This usually improves structure fidelity and dark-zone control.

## Metrics and Score (Higher Is Better)
Verifier computes:
- `nmse`: normalized RMSE between predicted intensity and target intensity
- `energy_in_target`: energy fraction where `target_amp > 0.30`
- `dark_suppression`: `1 - leak`, where leak is energy fraction in `target_amp < 0.03`

Score formula:
- `pattern_score = clip(1 - nmse / 4.0, 0, 1)`
- `energy_score = clip((energy_in_target - 0.10) / (0.70 - 0.10), 0, 1)`
- `dark_score = clip((dark_suppression - 0.35) / (0.90 - 0.35), 0, 1)`
- `score_pct = 100 * (0.55*pattern_score + 0.30*energy_score + 0.15*dark_score)`

Range: `0 ~ 100` (higher is better).

## Valid Criteria
Baseline is valid if:
- `score_pct >= 20`
- `energy_in_target >= 0.45`
- `dark_suppression >= 0.60`

## Expected Optimization Space
Typical high-impact improvements:
- iterative phase retrieval instead of one-shot inverse
- target-aware weighting for sparse structures
- strategies to penalize leakage in dark areas
- better initialization and iteration scheduling

