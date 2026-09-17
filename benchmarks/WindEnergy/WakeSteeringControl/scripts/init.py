from __future__ import annotations

from typing import Sequence


def yaw_policy(
    wind_directions_deg: Sequence[float],
    wind_speeds_mps: Sequence[float],
    turbulence_intensities: Sequence[float],
    layout_x_m: Sequence[float],
    layout_y_m: Sequence[float],
) -> list[list[float]]:
    """Return one yaw angle per wind condition and turbine.

    The shipped baseline applies no wake steering. Keep this function
    deterministic and preserve its signature.
    """

    n_conditions = len(wind_directions_deg)
    n_turbines = len(layout_x_m)

    # EVOLVE-BLOCK-START
    yaw_angles = [
        [0.0 for _ in range(n_turbines)]
        for _ in range(n_conditions)
    ]
    # EVOLVE-BLOCK-END

    return yaw_angles
