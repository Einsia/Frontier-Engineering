from __future__ import annotations

import unittest

import numpy as np

try:
    from verification.bsm1_model import (
        Q,
        BSM1Plant,
        action_energy,
        influent_at,
    )
except ModuleNotFoundError:
    from bsm1_model import Q, BSM1Plant, action_energy, influent_at


BASELINE_ACTION = {
    "kla3_per_day": 240.0,
    "kla4_per_day": 240.0,
    "kla5_per_day": 84.0,
    "internal_recycle_m3_per_day": 55338.0,
}


class BSM1ModelTests(unittest.TestCase):
    def test_reference_energy_matches_published_bsm1_operating_point(self) -> None:
        energy = action_energy(BASELINE_ACTION)
        self.assertAlmostEqual(energy["aeration"], 3341.3866666666663, places=9)
        self.assertAlmostEqual(energy["pumping"], 388.17, places=9)
        self.assertAlmostEqual(energy["mixing"], 240.0, places=9)

    def test_rain_adds_water_without_changing_component_mass_flow(self) -> None:
        time_day = 9.0
        dry = influent_at(time_day, "dry")
        rain = influent_at(time_day, "rain")
        self.assertAlmostEqual(rain[Q] - dry[Q], 20000.0, places=9)
        np.testing.assert_allclose(rain[:13] * rain[Q], dry[:13] * dry[Q], rtol=1e-12)

    def test_recycle_change_keeps_the_settler_hydraulically_valid(self) -> None:
        plant = BSM1Plant()
        action = dict(BASELINE_ACTION, internal_recycle_m3_per_day=30000.0)
        effluent = plant.step(influent_at(0.0, "dry"), action, 15.0 / 1440.0)
        self.assertTrue(np.all(np.isfinite(effluent)))
        self.assertGreater(effluent[Q], 0.0)
        self.assertAlmostEqual(effluent[Q], influent_at(0.0, "dry")[Q] - 385.0)


if __name__ == "__main__":
    unittest.main()
