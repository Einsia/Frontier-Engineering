from __future__ import annotations

import unittest

import numpy as np

try:
    from verification.bsm1_model import (
        Q,
        BSM1Plant,
        _asm1_rhs,
        _settler_rhs,
        _stream,
        action_energy,
        influent_at,
    )
except ModuleNotFoundError:
    from bsm1_model import (
        Q,
        BSM1Plant,
        _asm1_rhs,
        _settler_rhs,
        _stream,
        action_energy,
        influent_at,
    )


BASELINE_ACTION = {
    "kla3_per_day": 240.0,
    "kla4_per_day": 240.0,
    "kla5_per_day": 84.0,
    "internal_recycle_m3_per_day": 55338.0,
}


class BSM1ModelTests(unittest.TestCase):
    # These derivative oracles were generated independently with the
    # BSD-3-Clause bsm2-python equations at commit 73caa8b. Unlike invariant
    # checks, they detect stoichiometric, component-mapping, and flux-sign
    # regressions in the adapted implementation.
    def test_asm1_derivative_matches_bsm2_python_oracle(self) -> None:
        state = np.array(
            [30.0, 2.5, 1100.0, 75.0, 2500.0, 150.0, 440.0,
             1.7, 9.5, 4.2, 1.0, 4.5, 4.3]
        )
        feed = _stream(
            np.array(
                [30.0, 20.0, 100.0, 80.0, 300.0, 10.0, 50.0,
                 0.5, 5.0, 20.0, 4.0, 8.0, 6.0]
            ),
            75000.0,
            15.0,
        )
        expected = np.array(
            [
                0.0,
                -237.99652553781368,
                -56264.066016504126,
                -708.8242043304347,
                -122581.47155209856,
                -7835.430780772116,
                -21882.385746436612,
                -699.6350170215012,
                -76.41590901456709,
                649.7643483239231,
                145.0148701142897,
                152.66555899298714,
                65.93603488544677,
            ]
        )
        actual = _asm1_rhs(state, feed, kla=180.0, volume=1333.0)
        np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-9)

    def test_settler_derivative_matches_bsm2_python_oracle(self) -> None:
        components = np.array(
            [30.0, 0.9, 1100.0, 50.0, 2500.0, 150.0, 450.0,
             2.0, 12.0, 1.0, 0.7, 3.5, 4.0]
        )
        feed = _stream(components, 36892.0, 15.0)
        soluble_indices = [0, 1, 7, 8, 9, 10, 12]
        state = np.concatenate(
            [
                *(feed[index] * np.linspace(0.95, 1.05, 10)
                  for index in soluble_indices),
                np.array(
                    [15.0, 20.0, 30.0, 70.0, 350.0,
                     500.0, 800.0, 1500.0, 3000.0, 6500.0]
                ),
            ]
        )
        expected = np.array(
            [
                10.033888888888924, 10.033888888888924, 10.033888888888782,
                10.033888888889066, 10.247777777777287, -10.461666666666503,
                -10.461666666666645, -10.461666666666503, -10.461666666666929,
                -10.461666666666645, 0.3010166666666647, 0.30101666666666915,
                0.30101666666666915, 0.3010166666666647, 0.3074333333333268,
                -0.3138500000000022, -0.31384999999999774, -0.31384999999999774,
                -0.3138500000000066, -0.31384999999999774, 0.6689259259259295,
                0.6689259259259295, 0.6689259259259206, 0.6689259259259295,
                0.6831851851851756, -0.6974444444444394, -0.6974444444444394,
                -0.6974444444444483, -0.6974444444444572, -0.6974444444444394,
                4.013555555555541, 4.013555555555612, 4.013555555555541,
                4.013555555555612, 4.099111111111, -4.184666666666672,
                -4.184666666666601, -4.184666666666672, -4.184666666666743,
                -4.184666666666672, 0.33446296296296474, 0.33446296296296474,
                0.3344629629629603, 0.33446296296296474, 0.3415925925925878,
                -0.3487222222222197, -0.3487222222222197, -0.34872222222222415,
                -0.3487222222222286, -0.3487222222222197, 0.23412407407407354,
                0.23412407407407354, 0.23412407407407354, 0.23412407407407798,
                0.23911481481481367, -0.2441055555555538, -0.2441055555555538,
                -0.2441055555555538, -0.24410555555556268, -0.2441055555555538,
                1.337851851851859, 1.337851851851859, 1.3378518518518412,
                1.337851851851859, 1.3663703703703511, -1.3948888888888789,
                -1.3948888888888789, -1.3948888888888966, -1.3948888888889144,
                -1.3948888888888789, -159.27776512990226, -63.52879722181932,
                103.10310727314942, -476.22393432199857, 327.35724044926883,
                -121215.44270969188, -208086.76214135683, -155444.6724199591,
                403397.7099670557, 73152.46245290338,
            ]
        )
        actual = _settler_rhs(state, feed)
        np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-9)

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
