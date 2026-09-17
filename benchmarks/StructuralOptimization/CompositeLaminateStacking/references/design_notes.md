# Design and verification notes

## Provenance

This benchmark is an independent, NumPy-only adaptation of:

- J. H. S. Almeida Jr., E. Balonek, and S. G. P. Castro,
  *Dataset for Beyond Double-Double Theory: n-Directional Stacking Sequence
  Optimisation in Composite Laminates*, Zenodo,
  [doi:10.5281/zenodo.15864525](https://doi.org/10.5281/zenodo.15864525), MIT License.
- R. T. Haftka, *Optimization of Composite Structures*, 1993, including the
  48-ply square-plate reference case used by the released code.

The repository does not vendor the upstream optimizer or its dependencies. The material,
ply, geometry, loading, allowable-strain, and reference-layup values in `config.json` are
transcribed from the MIT-licensed release. The evaluator independently implements the
mechanics described below.

## Design encoding

The candidate returns 12 integer angles `theta_i` in `[0, 90]`. The verifier constructs
the first half of the laminate as:

```text
[theta_1, -theta_1, theta_2, -theta_2, ..., theta_12, -theta_12]
```

and mirrors that sequence to obtain 48 plies. Thus every accepted design is balanced and
symmetric by construction. Angles `90` and `-90` describe the same material direction.

## Classical lamination theory

The lamina reduced-stiffness matrix uses the released orthotropic properties
`E11`, `E22`, `nu12`, and `G12`. Each ply stiffness is transformed into global axes and
integrated through the thickness to form the laminate `A`, `B`, and `D` matrices. The
symmetry construction makes `B` zero to numerical precision.

## Maximum-strain failure factor

For each nominal membrane load, the evaluator solves:

```text
epsilon_0 = A^-1 N
```

after applying the released 1.5 design-load factor. Global strains are transformed into
every ply's material axes. The failure load factor is the smallest ratio between the
released allowable longitudinal, transverse, and shear strains and the corresponding
absolute ply strain.

## Buckling factor

The verifier approximates a simply supported plate with a double-sine Ritz basis. It
integrates bending and geometric stiffness with Gauss-Legendre quadrature, preserving
`D16` and `D26` coupling, and solves the symmetric generalized eigenproblem. Five modes
per direction are used in the committed configuration.

For the released square biaxial anchor, the upstream code reports a failure factor of
`10394.81` and a BFSC finite-element buckling factor of `9998.19`. The independent
implementation returns approximately `10396.48` and `10430.16`, respectively: failure
agrees within 0.1%, and the lower-order Ritz buckling approximation agrees within 5%.
These bounds are enforced by regression tests.

## Ranking score

For each case, engineering performance is the governing reserve factor:

```text
reserve = min(failure_load_factor, buckling_load_factor)
```

The case score is centered at 50 for the released Haftka reference layup and varies
smoothly with the logarithm of the candidate-to-anchor reserve ratio. The final score is
75% mean case score plus 25% twentieth-percentile case score. Invalid or incomplete
candidate output receives `combined_score = 0`, while per-case errors remain visible.

The anchor only normalizes task difficulty. It is not an optimum: a simple load-aware
design exceeds 60 points in the regression suite, leaving measurable optimization room.
