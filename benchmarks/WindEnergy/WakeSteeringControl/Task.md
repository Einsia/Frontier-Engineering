# Task: Wind-Farm Wake-Steering Control

## Background

An upstream turbine extracts energy and leaves a slower wake. When turbines are
aligned with the wind, that wake can reduce the production of downstream
turbines. Deliberately yawing an upstream rotor can redirect its wake. The
upstream turbine loses some power, but the farm may gain more power overall.

## Objective

Implement `yaw_policy()` in `scripts/init.py`. For each wind condition, return
one yaw angle per turbine. Maximize frequency-weighted farm energy relative to
the zero-yaw baseline while avoiding excessive yaw and abrupt changes between
nearby wind directions.

## Inputs

The policy receives Python lists:

- `wind_directions_deg`: meteorological wind directions in degrees;
- `wind_speeds_mps`: wind speeds in metres per second;
- `turbulence_intensities`: dimensionless turbulence intensity values;
- `layout_x_m`, `layout_y_m`: fixed turbine coordinates in metres.

There are `n_conditions` wind conditions and `n_turbines` layout points.

## Output

Return a rectangular nested list or compatible numeric array with shape:

```text
(n_conditions, n_turbines)
```

Every value is a yaw angle in degrees and must lie in `[-25, 25]`. Positive and
negative signs represent opposite steering directions under FLORIS conventions.

## Score

The verifier computes weighted expected farm power for the candidate and the
zero-yaw baseline. The higher-is-better score is:

```text
relative energy gain in percentage points
- 0.01 * frequency-weighted mean absolute yaw in degrees
- 0.002 * mean adjacent-direction yaw change in degrees
```

The zero-yaw baseline therefore scores approximately `0.0`. Raw energy and
penalty components are reported separately.

## Hard Constraints

- Return the exact required shape and only finite numeric values.
- Keep every yaw angle within `[-25, 25]` degrees.
- Return identical results for identical inputs.
- Complete within the candidate timeout.
- Do not modify benchmark, reference, or verifier files.
- Keep the function signature and EVOLVE markers unchanged.

The verifier determines feasibility and score. During unified evaluation,
Frontier Eval also invalidates candidates that modify files declared read-only.
