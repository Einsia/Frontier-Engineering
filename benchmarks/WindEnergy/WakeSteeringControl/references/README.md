# Public Configuration

`farm_config.json` defines the public farm geometry, yaw limits, timeout, and
score coefficients. Coordinates are expressed in rotor-diameter multiples and
are converted to metres using the NREL 5 MW rotor diameter loaded by FLORIS.

The evaluator owns the deterministic wind-condition ensemble. A candidate
receives every condition it must control through the documented policy inputs.
