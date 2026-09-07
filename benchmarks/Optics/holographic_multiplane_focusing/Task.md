# Holographic H2 Specification: Multi-Plane Focusing

## Engineering background

Task 1 is single-plane focusing. Task 2 adds **depth**.

You now need one optical stack that works at multiple distances `z`:

- same hardware parameters,
- different desired patterns on different output planes.

Think of it as one model serving multiple views/slices, where each depth has its own target ratio.

Typical applications:

- 3D optical trapping,
- volumetric laser processing,
- depth-multiplexed projection.

Economic value:

- one optical component serving multiple depth functions reduces system complexity and calibration cost.

## What you need to do

Improve optimization in baseline so that all planes are satisfied better under the task score.

Editable area:

- `baseline/init.py`

Read-only for challenge use:

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

- `shape`, `spacing`, `wavelength`, `waist_radius`, `layer_z` -- the shared stack.
- `planes` -- a list of plane configs; each has `z`, `centers` and `ratios`.
- `roi_radius_m` -- radius used to measure each spot's power.
- `steps`, `lr` -- the optimisation budget the evaluator advertises.
- scoring constants: `score_eff_target`, `score_ratio_scale`, `valid_*`.

`problem.json["submission"]` restates the exact array names, shapes and bounds
your submission must satisfy.

## Output contract (`submission.npz`)

Write **decision variables only** -- plain real-valued arrays:

- `phases`: `float64`, shape `(n_layers, shape, shape)` -- the phase map of each
  `PhaseModulator`, in the order of `layer_z`. Values in radians, `|phase| <= 1e4`.

One shared stack must serve every plane in `planes`; there is no per-plane mask.

Optional, diagnostics only (never scored): `loss_history`, a 1-D float array.

`verification/evaluate.py` then does all of the following itself:

1. builds the `PhaseModulator` stack from your `phases`,
2. builds the Gaussian input field,
3. propagates it to every `z` in `planes`,
4. builds each plane's target from its `centers` / `ratios`,
5. computes per-plane `ratio_mae`, `efficiency`, `shape_cosine`, and the mean score.

Consequences you should design for:

- Returning a `system`, an `input_field`, a `target_field` or a self-reported
  score/metric has **no effect** -- nothing but the named arrays is read.
- `submission.npz` is loaded with `allow_pickle=False`, so only arrays survive.
- Arrays are validated for shape, dtype, finiteness and range. A crash, a
  timeout, a missing `submission.npz` or an out-of-range array is a hard
  rejection (`combined_score = -1e18`), not a low score.

## Baseline implementation (current)

Current baseline is intentionally weak:

1. Build one input Gaussian field.
2. Build one target field per plane.
3. Compute overlap loss on each plane.
4. Average plane losses and optimize with Adam.

What it misses:

- no explicit ratio objective,
- no explicit leakage/efficiency control,
- no adaptive weighting for hard planes.

## Oracle implementation (current)

`verification/reference_solver.py` is stronger:

1. Run `slmsuite` WGS per plane to generate phase seeds.
2. Fuse seeds into multi-layer initialization.
3. Fine-tune with composite objective per plane:
   - overlap,
   - ratio error,
   - leakage.
4. Reweight harder planes dynamically during training.

This is a stronger engineering baseline for comparison.

## Metrics and score (0~1)

For each plane `m`:

- `ratio_mae_m`
- `efficiency_m = P_focus_m / P_total_m`
- `shape_cosine_m = cosine(I_pred_norm_m, I_target_norm_m)`

Derived per-plane components:

- `ratio_score_m = exp(-ratio_mae_m / score_ratio_scale)`
- `efficiency_score_m = min(1, efficiency_m / score_eff_target)`

Per-plane score:

- `score_m = (efficiency_score_m^0.50) * (ratio_score_m^0.35) * (shape_cosine_m^0.15)`

Global metrics:

- `mean_ratio_mae`
- `mean_efficiency`
- `mean_shape_cosine`
- `mean_score = average(score_m)`

Interpretation:

- score near `1`: high efficiency + accurate ratios + close target maps across planes,
- score near `0`: failing on one or more planes severely.

## Valid and better-than-baseline logic

Baseline `valid=True` iff:

- `mean_ratio_mae <= valid_mean_ratio_mae_max`
- `mean_efficiency >= valid_mean_efficiency_min`
- `mean_score >= valid_mean_score_min`

Reference `better_than_baseline=True` iff:

- `reference_mean_score >= baseline_mean_score + better_score_margin`
- `reference_mean_shape_cosine >= baseline_mean_shape_cosine + better_shape_margin`

## Verification artifacts and how to read them

Generated under `verification/artifacts/`:

- `summary.json`
  - full metrics/spec/timing + pass/fail/comparison flags.
- `plane_intensity_maps.png`
  - for each plane: target / baseline / reference intensity maps.
- `loss_and_efficiency.png`
  - loss curves + per-plane efficiency bars.

How to debug quickly:

- if ratio is wrong but spot positions are right: improve ratio-specific terms,
- if efficiency is low everywhere: improve leakage/energy concentration objective,
- if only one plane fails: use plane-aware weighting/curriculum.

## Run verification

```bash
PY=python3
$PY benchmarks/Optics/holographic_multiplane_focusing/verification/evaluate.py --device cpu
```

