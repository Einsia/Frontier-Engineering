from __future__ import annotations

import unittest

import numpy as np

try:
    from verification.mechanics import (
        evaluate_base_angles,
        expand_balanced_symmetric,
        laminate_abd,
        load_config,
        normalize_base_angles,
        public_cases,
    )
except ModuleNotFoundError:
    from mechanics import (
        evaluate_base_angles,
        expand_balanced_symmetric,
        laminate_abd,
        load_config,
        normalize_base_angles,
        public_cases,
    )


class MechanicsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.anchor = list(self.config["anchor_base_angles_deg"])

    def test_expansion_is_balanced_and_symmetric(self) -> None:
        stack = expand_balanced_symmetric(self.anchor)
        self.assertEqual(len(stack), 48)
        self.assertEqual(stack, list(reversed(stack)))
        for angle in set(abs(value) for value in stack):
            if angle == 0:
                continue
            self.assertEqual(stack.count(angle), stack.count(-angle))

    def test_symmetric_laminate_has_negligible_coupling_matrix(self) -> None:
        stack = expand_balanced_symmetric(self.anchor)
        _, coupling, _ = laminate_abd(stack, self.config)
        self.assertLess(float(np.max(np.abs(coupling))), 1e-7)

    def test_reference_design_produces_positive_finite_factors(self) -> None:
        for case in public_cases(self.config):
            result = evaluate_base_angles(self.anchor, case, self.config)
            for value in result.values():
                self.assertTrue(np.isfinite(value))
                self.assertGreater(value, 0.0)

    def test_square_biaxial_case_matches_upstream_reference(self) -> None:
        case = next(
            item for item in public_cases(self.config) if item["case_id"] == "biaxial_ar_1_0"
        )
        result = evaluate_base_angles(self.anchor, case, self.config)
        # The MIT-licensed source reports lambda_cs=10394.81 and lambda_cb=9998.19.
        # Failure uses the same closed-form maximum-strain calculation. Buckling uses
        # an independent Ritz implementation instead of the source BFSC finite element.
        self.assertAlmostEqual(result["failure_load_factor"] / 10394.81, 1.0, delta=0.001)
        self.assertAlmostEqual(result["buckling_load_factor"] / 9998.19, 1.0, delta=0.05)

    def test_angle_schema_reports_specific_error(self) -> None:
        angles, error = normalize_base_angles([45] * 11 + [90.5], self.config)
        self.assertIsNone(angles)
        self.assertEqual(error, "angle[11] must be a finite integer")


if __name__ == "__main__":
    unittest.main()
