# Holographic H1 Specification: Multifocus Power-Ratio Control

## Engineering background

You can think of this task as "image formation by a physical compiler":

- Input: one laser beam (a 2D field).
- Program: a small stack of trainable phase masks.
- Output: intensity pattern on a target plane.

Goal: produce **6 bright spots** at specified coordinates, and make their relative brightness follow a required ratio.

Why this matters in engineering:

- parallel laser machining (multiple processing points at once),
- optical tweezers (multiple trap sites),
- multi-channel optical coupling.

Economic relevance:

- better optical throughput and precision can increase yield and reduce process time.

## What you need to do

You are expected to improve the baseline optimization strategy so that the output is closer to the target under the task score.

The challenge setup is:

- editable target: `baseline/init.py`,
- evaluator and oracle are in `verification/` and should be treated as read-only.

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

- `shape`, `spacing`, `wavelength`, `waist_radius` -- the grid and the source.
- `layer_z` -- z position of each trainable phase layer.
- `output_z` -- the observation plane.
- `focus_centers` -- the 6 target spot coordinates `(x, y)`, in metres.
- `focus_ratios` -- the target relative power of each spot.
- `roi_radius_m` -- radius used to measure each spot's power.
- `steps`, `lr` -- the optimisation budget the evaluator advertises.
- scoring constants: `score_eff_target`, `score_ratio_scale`, `valid_*`.

`problem.json["submission"]` restates the exact array names, shapes and bounds
your submission must satisfy.

## Output contract (`submission.npz`)

Write **decision variables only** -- plain real-valued arrays:

- `phases`: `float64`, shape `(n_layers, shape, shape)` -- the phase map of each
  `PhaseModulator`, in the order of `layer_z`. Values in radians, `|phase| <= 1e4`.

Optional, diagnostics only (never scored): `loss_history`, a 1-D float array.

`verification/evaluate.py` then does all of the following itself:

1. builds the `PhaseModulator` stack from your `phases`,
2. builds the Gaussian input field,
3. propagates it to `output_z`,
4. builds the target field from `focus_centers` / `focus_ratios`,
5. computes `ratio_mae`, `efficiency`, `shape_cosine` and the final score.

Consequences you should design for:

- Returning a `system`, an `input_field`, a `target_field` or a self-reported
  score/metric has **no effect** -- nothing but the named arrays is read.
- `submission.npz` is loaded with `allow_pickle=False`, so only arrays survive.
- Arrays are validated for shape, dtype, finiteness and range. A crash, a
  timeout, a missing `submission.npz` or an out-of-range array is a hard
  rejection (`combined_score = -1e18`), not a low score.

## Baseline implementation (what it currently does)

Current baseline is intentionally simple:

1. Build Gaussian input field.
2. Build target field from 6 Gaussians weighted by target ratios.
3. Optimize phase layers with overlap-only objective:
   - `loss = 1 - |<output, target>|^2`
4. Use Adam for fixed steps.

Limitations by design:

- no direct ratio loss,
- no explicit leakage penalty,
- no curriculum/staged training.

## Oracle implementation (comparison reference)

`verification/reference_solver.py` is stronger and may use third-party tools:

1. Use `slmsuite` WGS to generate a high-quality phase seed.
2. Initialize optical layers from this seed.
3. Fine-tune with composite objective:
   - overlap term,
   - ratio error term,
   - leakage term,
   - phase smoothness regularizer.

This is intended as a stronger engineering reference, not a baseline.

## Metrics and score (0 to 1, higher is better)

Measured on output intensity:

- `ratio_mae`: mean absolute error of predicted focus ratios.
- `efficiency`: fraction of total energy inside all focus ROIs.
- `shape_cosine`: cosine similarity between normalized predicted and target intensity maps.

Derived:

- `ratio_score = exp(-ratio_mae / score_ratio_scale)`
- `efficiency_score = min(1, efficiency / score_eff_target)`

Final score:

- `score = (efficiency_score^0.58) * (ratio_score^0.22) * (shape_cosine^0.20)`

Interpretation:

- close to `1.0`: high efficiency, correct ratios, close target shape,
- around `0.2~0.4`: partially correct but significant deficits,
- near `0`: mostly failing objective.

## Valid and better-than-baseline logic

Baseline is `valid=True` iff all hold:

- `ratio_mae <= valid_ratio_mae_max`
- `efficiency >= valid_efficiency_min`
- `score >= valid_score_min`

Reference is `better_than_baseline=True` iff all hold:

- `reference_score >= baseline_score + better_score_margin`
- `reference_shape_cosine >= baseline_shape_cosine + better_shape_margin`

## Verification artifacts and how to read them

`verification/evaluate.py` writes to `verification/artifacts/`:

- `summary.json`:
  - machine-readable result summary,
  - includes spec, runtime, metrics, score, valid flag, and comparison verdict.
- `intensity_maps.png`:
  - side-by-side target vs baseline vs reference intensity maps,
  - quickest visual check for whether spots are at correct positions.
- `ratios_and_losses.png`:
  - bar chart of target/baseline/reference spot ratios,
  - training-loss curves for baseline/reference.

## Running verification

```bash
PY=python3
$PY benchmarks/Optics/holographic_multifocus_power_ratio/verification/evaluate.py --device cpu
```

Optional flags:

- `--seed`
- `--baseline-steps`
- `--reference-steps`
- `--artifacts-dir`

