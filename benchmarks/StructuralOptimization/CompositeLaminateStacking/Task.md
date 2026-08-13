# Task: Composite Laminate Stacking Optimization

## 1. Engineering problem

Design the stacking sequence of a 48-ply orthotropic composite plate. A good laminate
must resist both material failure and plate buckling under several geometries and load
ratios. This is a discrete, coupled structural-design problem: moving stiff plies toward
the surfaces can help buckling, while changing fiber directions alters in-plane strength
and can hurt another load case.

The task is derived from the MIT-licensed Zenodo release *Beyond Double-Double Theory:
n-Directional Stacking Sequence Optimisation in Composite Laminates*
([doi:10.5281/zenodo.15864525](https://doi.org/10.5281/zenodo.15864525)). It preserves
the released 48-ply construction, orthotropic material, ply thickness, five aspect ratios,
uniaxial/biaxial compression, strain allowables, and Haftka reference layup. The evaluator
is an independent NumPy implementation documented in `references/design_notes.md`.

## 2. Candidate API

Implement in `scripts/init.py`:

```python
def design_laminates(cases: list[dict]) -> dict[str, list[int]]:
    ...
```

The function receives all public cases in one call. Each case contains only:

```python
{
    "case_id": str,
    "aspect_ratio": float,
    "a_mm": float,
    "b_mm": float,
    "Nx_N_per_mm": float,
    "Ny_N_per_mm": float,
}
```

Compression is negative. `Ny_N_per_mm == 0` denotes uniaxial loading; a negative value
denotes biaxial compression.

Return a dictionary with exactly the supplied `case_id` values. Each value must be a JSON
list containing exactly 12 finite integer angles in the inclusive interval `[0, 90]`.

## 3. Layup construction

For candidate angles `theta_1 ... theta_12`, the verifier constructs the first half as:

```text
[theta_1, -theta_1, theta_2, -theta_2, ..., theta_12, -theta_12]
```

and appends its reverse. The result has 48 plies and is balanced and symmetric by
construction. The candidate therefore optimizes both angle selection and through-thickness
ordering without needing to implement manufacturing-constraint repair.

## 4. Evaluation cases

Ten deterministic cases combine aspect ratios `0.5, 1, 2, 3, 4` with:

- uniaxial compression: `Nx = -0.175126835 N/mm`, `Ny = 0`;
- biaxial compression: `Nx = -0.175126835 N/mm`, `Ny = -0.087563418 N/mm`.

The plate widths are fixed at `127 mm`; lengths vary with aspect ratio. Material and
allowable values are committed in `references/config.json`.

## 5. Physics

The verifier applies classical lamination theory to compute `A`, `B`, and `D`. It then
computes:

1. a maximum-strain failure load factor from the most critical longitudinal, transverse,
   or shear ply strain under the released 1.5 design-load factor;
2. a simply supported plate buckling load factor from a double-sine Ritz basis, numerical
   quadrature, and a symmetric generalized eigenproblem.

The governing reserve factor is:

```text
reserve = min(failure_load_factor, buckling_load_factor)
```

## 6. Score

Each case is normalized against the released Haftka reference stacking sequence:

```text
case_score = clip(50 + 50*tanh(log(reserve/anchor_reserve)/0.5), 0, 100)
```

The final diagnostic score is:

```text
0.75 * mean(case_scores) + 0.25 * percentile(case_scores, 20)
```

A valid candidate receives that value as `combined_score`. Missing cases, extra case ids,
bad types, non-integer/out-of-range angles, timeouts, import failures, or invalid mechanics
make the candidate invalid and set `combined_score` to zero. Per-case diagnostic feedback
remains available.

## 7. Runtime and integrity contract

- Keep `design_laminates` deterministic and self-contained.
- Candidate import and execution occur in a separate Python process with a bounded runtime.
- The process receives cases and returns designs through a JSON-lines protocol.
- Candidate stdout is discarded so it cannot corrupt the evaluator protocol.
- This is process isolation, not an operating-system security sandbox.
- Do not read or modify evaluator, reference, output, or environment-secret files.
- Edit only the region between the `EVOLVE-BLOCK` markers in `scripts/init.py`.

## 8. Commands

Direct evaluation, from this directory:

```bash
python verification/evaluator.py scripts/init.py
```

Unified evaluation, from the repository root:

```bash
python -m frontier_eval task=unified \
  task.benchmark=StructuralOptimization/CompositeLaminateStacking \
  algorithm=openevolve algorithm.iterations=0
```
