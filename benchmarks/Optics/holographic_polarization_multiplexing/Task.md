# Holographic H4 Specification: Polarization Multiplexing

## Engineering background

In polarization multiplexing, the same optical element should behave differently for different input polarization states.

In this task:

- x-polarized input should produce pattern X,
- y-polarized input should produce pattern Y,
- and cross-channel leakage should be low.

CS analogy:

- one shared model,
- two input modes,
- mode-conditioned outputs must be different and controlled.

Applications:

- polarization-division multiplexing,
- optical security,
- multifunctional diffractive/meta-optics.

Economic value:

- one element providing multiple functions lowers hardware count and integration cost.

## What you need to do

Improve baseline optimization so the design better separates polarization channels while matching per-channel target patterns and ratios.

Editable file:

- `baseline/init.py`

Read-only references:

- `verification/evaluate.py`
- `verification/reference_solver.py`

## Core file/function to modify

- `baseline/init.py`
- Core function: `solve(spec, device=None, seed=0)`

You may add or change helpers in the same file. Keep the
`if __name__ == "__main__":` block at the bottom: it is the evaluation entry
point.

## How your program is run

Your file is executed as **its own process**, in a throwaway directory that
contains exactly two files:

- `problem.json` -- the problem, as data (written by the evaluator),
- a copy of `baseline/init.py` -- your program.

The task tree, `verification/`, the oracle and the evaluator are not available
to the candidate process. Read `problem.json` from the current directory and
write `submission.npz` to the current directory.

## Input contract (`problem.json`)

The problem definition is owned by `verification/problem_spec.py` and is
identical for every submission. It is read-only and is loaded by the evaluator
*before* your process starts.

Fields you receive:

- `shape`, `spacing`, `wavelength`, `waist_radius`, `layer_z`, `output_z`.
- `pattern_x_centers` / `pattern_x_ratios` -- the pattern the x-polarised input
  must produce.
- `pattern_y_centers` / `pattern_y_ratios` -- likewise for the y-polarised input.
- `roi_radius_m` -- ROI radius for power measurement.
- `steps`, `lr` -- the optimisation budget the evaluator advertises.
- scoring constants: `score_eff_target`, `score_ratio_scale`, `valid_*`.

`problem.json["submission"]` restates the exact array names, shapes and bounds
your submission must satisfy.

## Output contract (`submission.npz`)

Write **decision variables only** -- plain real-valued arrays:

- `phase_x`: `float64`, shape `(n_layers, shape, shape)` -- the Jones `[0,0]`
  phase of each layer, in the order of `layer_z`.
- `phase_y`: `float64`, same shape -- the Jones `[1,1]` phase of each layer.

Both in radians, `|phase| <= 1e4`.

Optional, diagnostics only (never scored): `loss_history`, a 1-D float array.

`verification/evaluate.py` then does all of the following itself:

1. builds both polarised Gaussian input fields,
2. for each layer: `propagate_to_z(layer_z[i])` then `polarized_modulate` with
   `diag(exp(1j*phase_x[i]), exp(1j*phase_y[i]), 1)`,
3. propagates to `output_z`,
4. builds both target maps from the `pattern_*` fields,
5. computes match, separation, own-efficiency, ratio error and the final score.

Consequences you should design for:

- Returning a `system`, an `input_field`, a `target_field` or a self-reported
  score/metric has **no effect** -- nothing but the named arrays is read.
- `submission.npz` is loaded with `allow_pickle=False`, so only arrays survive.
- Arrays are validated for shape, dtype, finiteness and range. A crash, a
  timeout, a missing `submission.npz` or an out-of-range array is a hard
  rejection (`combined_score = -1e18`), not a low score.

## Baseline implementation (current)

Current baseline is intentionally simple:

1. Build x-polarized and y-polarized Gaussian inputs.
2. Use diagonal Jones phase layers (separate phase maps for Ex/Ey channels).
3. Optimize normalized map MSE for both channels.

What it does not explicitly optimize:

- channel crosstalk,
- per-channel ratio accuracy,
- channel own-efficiency.

## Oracle implementation (current)

`verification/reference_solver.py` is stronger:

1. Build separate `slmsuite` WGS seeds for x-target and y-target.
2. Initialize polarization phase layers from these seeds.
3. Fine-tune with composite objective:
   - target map matching,
   - crosstalk suppression,
   - ratio matching,
   - intended-channel efficiency,
   - phase smoothness regularization.

This yields a stronger practical reference.

## Metrics and score (0~1)

Core metrics:

- `match_x`, `match_y`, `mean_match`: cosine similarity to target maps.
- `separation_x`, `separation_y`, `separation`: how well each polarization stays in its own target ROIs.
- `own_efficiency`: fraction of power on intended channel targets.
- `ratio_mae_x`, `ratio_mae_y`, `mean_ratio_mae`: per-channel ratio errors.

Derived components:

- `ratio_score = exp(-mean_ratio_mae / score_ratio_scale)`
- `efficiency_score = min(1, own_efficiency / score_eff_target)`

Final score:

- `score = (separation^0.55) * (ratio_score^0.20) * (efficiency_score^0.25) * (mean_match^0.05)`

Interpretation:

- this score emphasizes **channel separation** and **useful in-channel power**,
- map similarity still matters, but is not the dominant term.

## Valid and better-than-baseline logic

Baseline is valid iff:

- `mean_match >= valid_match_min`
- `separation >= valid_separation_min`
- `score >= valid_score_min`

Reference is better iff:

- `reference_score >= baseline_score + better_score_margin`
- `reference_separation >= baseline_separation + better_sep_margin`

## Verification artifacts and their meaning

Saved under `verification/artifacts/`:

- `summary.json`
  - complete structured result (metrics, score, timing, pass/fail/comparison).
- `polarization_maps.png`
  - target/baseline/reference maps for x-input and y-input channels.
- `loss_and_metrics.png`
  - loss curves,
  - compact bar comparison (`match`, `separation`, `ratio_score`, `score`).

Quick diagnosis:

- high match but low separation: channel leakage problem,
- high separation but poor ratio_score: local energy split mismatch,
- low efficiency_score: not enough power in intended ROIs.

## Run verification

```bash
PY=python3
$PY benchmarks/Optics/holographic_polarization_multiplexing/verification/evaluate.py --device cpu
```

