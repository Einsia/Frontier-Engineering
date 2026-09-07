# Holographic H3 Specification: Multi-Wavelength Focusing/Splitting

## Engineering background

Different wavelengths (colors) naturally propagate differently.

In many products, one optical element must satisfy all of them simultaneously:

- each wavelength should go to a designated spatial target,
- total power split across wavelengths should match a desired ratio.

This is similar to a multi-domain optimization problem:

- domains = wavelengths,
- each domain has a spatial target,
- global coupling constraint = spectral ratio.

Applications:

- color imaging optics,
- WDM optical routing,
- chromatic compensation components.

Economic value:

- better multi-wavelength behavior improves product quality without adding extra hardware channels.

## What you need to do

Improve baseline optimization in `baseline/init.py` to get higher score under shared-hardware constraints.

Editable target:

- `baseline/init.py`

Read-only in challenge setup:

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

Nothing else is reachable from there: the task tree, `verification/`, the oracle
and the evaluator are all absent and not importable. You read `problem.json` from
the current directory and write `submission.npz` to the current directory.

## Input contract (`problem.json`)

The problem definition is owned by `verification/problem_spec.py` and is
identical for every submission. It is read-only and is loaded by the evaluator
*before* your process starts.

Fields you receive:

- `shape`, `spacing`, `waist_radius`, `layer_z`, `output_z` -- the geometry.
- `wavelengths` -- the four wavelengths sharing the same hardware.
- `refractive_index` -- the medium's (constant) refractive index `n`.
- `target_centers` -- one target coordinate per wavelength.
- `target_spectral_ratios` -- the desired power split across wavelengths.
- `roi_radius_m` -- ROI radius for energy measurement.
- `steps`, `lr`, `init_thickness_mean`, `init_thickness_std`, `num_restarts` --
  the optimisation budget the evaluator advertises.
- scoring constants: `score_eff_target`, `score_spectral_scale`, `valid_*`.

`problem.json["submission"]` restates the exact array names, shapes and bounds
your submission must satisfy.

## Output contract (`submission.npz`)

Write **decision variables only** -- plain real-valued arrays:

- `thickness`: `float64`, shape `(n_layers, shape, shape)` -- the **physical
  thickness** of each layer in metres, in the order of `layer_z`, bounded to
  `[0, max_thickness_m]`.

The design variable is a thickness, not a phase, because one physical profile
imprints a *wavelength-dependent* phase

    phi(x, y; lambda) = 2*pi/lambda * (n - 1) * t(x, y)

which is what makes this a shared-hardware problem rather than four independent
single-wavelength holograms.

Optional, diagnostics only (never scored): `loss_history`, a 1-D float array.

`verification/evaluate.py` then does all of the following itself:

1. builds the dispersive `PolychromaticPhaseModulator` stack from your `thickness`,
2. builds one Gaussian input field per wavelength,
3. propagates each of them to `output_z`,
4. computes per-wavelength efficiency, crosstalk and shape cosine,
5. computes the spectral ratio error and the final score.

The oracle in `verification/reference_solver.py` is deliberately allowed a
*per-wavelength* phase mask (four independent holograms). That relaxation is an
upper bound chosen by the evaluator, is recorded in `summary.json` as
`reference.design_space`, and is not available to submissions.

Consequences you should design for:

- Returning a `system`, an `input_field`, a `target_field` or a self-reported
  score/metric has **no effect** -- nothing but the named arrays is read.
- `submission.npz` is loaded with `allow_pickle=False`, so only arrays survive.
- Arrays are validated for shape, dtype, finiteness and range. A crash, a
  timeout, a missing `submission.npz` or an out-of-range array is a hard
  rejection (`combined_score = -1e18`), not a low score.

## Baseline implementation (current)

Current baseline is intentionally minimal:

1. Build one shared dispersive thickness stack (`PolychromaticPhaseModulator`).
2. For each wavelength, optimize target-ROI efficiency with a crosstalk term.
3. Average loss across wavelengths, clamping thickness into its bounds each step.

Missing pieces (deliberate):

- no explicit crosstalk suppression,
- no explicit spectral-ratio matching,
- no advanced initialization.

## Oracle implementation (current)

Reference is stronger and less hardware-constrained:

1. Use `slmsuite` WGS to generate seed phase map per wavelength.
2. Build two candidates:
   - direct wavelength-specific phase execution,
   - wavelength-specific phase fine-tuning.
3. Select candidate with better task score.

Because phases are wavelength-specific (not one strictly shared mask), this behaves as an upper-bound reference.

## Metrics and score (0~1)

Per wavelength `i`:

- `target_efficiency_i = P_target_i / P_total_i`
- `designated_crosstalk_i = P_other_designated_i / (P_target_i + P_other_designated_i)`
- `shape_cosine_i = cosine(I_pred_norm_i, I_target_norm_i)`

Global:

- `mean_target_efficiency`
- `mean_crosstalk`
- `mean_shape_cosine`
- `spectral_ratio_mae`

Derived components:

- `efficiency_score = min(1, mean_target_efficiency / score_eff_target)`
- `isolation_score = 1 - mean_crosstalk`
- `spectral_score = exp(-spectral_ratio_mae / score_spectral_scale)`

Final score:

- `mean_score = (efficiency_score^0.45) * (isolation_score^0.25) * (spectral_score^0.20) * (mean_shape_cosine^0.10)`

Interpretation:

- high score needs both spatial correctness and spectral correctness,
- strong spectral ratio with poor spatial map (or inverse) cannot get top score.

## Valid and better-than-baseline logic

Baseline is valid iff:

- `mean_target_efficiency >= valid_mean_target_efficiency_min`
- `mean_crosstalk <= valid_mean_crosstalk_max`
- `mean_score >= valid_mean_score_min`

Reference is better iff:

- `reference_mean_score >= baseline_mean_score + better_score_margin`
- `reference_mean_shape_cosine >= baseline_mean_shape_cosine + better_shape_margin`

## Verification artifacts and their meaning

Outputs under `verification/artifacts/`:

- `summary.json`
  - all metrics, scores, timing, and pass/fail flags.
- `spectral_intensity_maps.png`
  - per wavelength: target vs baseline vs reference maps.
- `loss_and_spectral_ratios.png`
  - loss curves,
  - bar chart of target/baseline/reference spectral ratios.

Typical debugging signals:

- low spectral score + decent maps: need explicit ratio loss,
- high crosstalk: need stronger designated-vs-other suppression,
- low shape cosine: improve initialization/objective balance.

## Run verification

```bash
PY=python3
$PY benchmarks/Optics/holographic_multispectral_focusing/verification/evaluate.py --device cpu
```

