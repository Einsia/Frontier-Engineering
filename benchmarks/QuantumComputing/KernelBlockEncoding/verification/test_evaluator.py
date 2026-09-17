"""Focused standard-library tests for the kernel block-encoding evaluator."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import evaluator


class KernelBlockEncodingTests(unittest.TestCase):
    def test_integer_partial_hadamard_transform(self) -> None:
        transformed, denominator = evaluator._basis_transform((1, 2, 3, 4), 2, 1)
        self.assertEqual(transformed, [10, -2, -4, 0])
        self.assertEqual(denominator, 2)

    def test_identity_round_trip_and_error_rejection(self) -> None:
        config = evaluator._validated_config()
        scale = int(config["matrix_scale"])
        angle_denominator = int(config["angle_denominator"])
        workload = evaluator.Workload(
            workload_id="identity_2",
            dimension=2,
            matrix_scale=scale,
            epsilon_numerator=2,
            matrix=(scale, 0, 0, scale),
            input_bytes=b"test",
            sha256="0" * 64,
        )
        entry_ticks = [0, angle_denominator, angle_denominator, 0]
        coefficients = list(entry_ticks)
        stride = 1
        while stride < len(coefficients):
            for base in range(0, len(coefficients), 2 * stride):
                for offset in range(stride):
                    lhs = coefficients[base + offset]
                    rhs = coefficients[base + offset + stride]
                    coefficients[base + offset] = (lhs + rhs) // 2
                    coefficients[base + offset + stride] = (lhs - rhs) // 2
            stride *= 2
        gray_coefficients = tuple(
            coefficients[evaluator._gray_code(index)]
            for index in range(len(coefficients))
        )
        certificate = evaluator.Certificate(
            basis_mask=0,
            scale_numerator=scale,
            angle_ticks=gray_coefficients,
            sha256="1" * 64,
            byte_count=1,
        )
        checked = evaluator._check_construction(certificate, workload, config)
        self.assertLess(checked.error_upper_bound, workload.epsilon)
        self.assertAlmostEqual(checked.alpha, 2.0)
        self.assertEqual(checked.qubits, 3)

        invalid = evaluator.Certificate(
            basis_mask=0,
            scale_numerator=scale,
            angle_ticks=(0, 0, 0, 0),
            sha256="2" * 64,
            byte_count=1,
        )
        with self.assertRaises(evaluator.EvaluationError):
            evaluator._check_construction(invalid, workload, config)

    def test_walsh_gray_schedule_realizes_multiplexed_rotations(self) -> None:
        entry_angles = [0.2, 0.8, 1.4, 2.2]
        coefficients = list(entry_angles)
        stride = 1
        while stride < len(coefficients):
            for base in range(0, len(coefficients), 2 * stride):
                for offset in range(stride):
                    lhs = coefficients[base + offset]
                    rhs = coefficients[base + offset + stride]
                    coefficients[base + offset] = (lhs + rhs) / 2
                    coefficients[base + offset + stride] = (lhs - rhs) / 2
            stride *= 2
        gray_coefficients = [
            coefficients[evaluator._gray_code(index)]
            for index in range(len(coefficients))
        ]

        def multiply(
            lhs: list[list[float]], rhs: list[list[float]]
        ) -> list[list[float]]:
            return [
                [
                    sum(
                        lhs[row][inner] * rhs[inner][column]
                        for inner in range(2)
                    )
                    for column in range(2)
                ]
                for row in range(2)
            ]

        def rotation(angle: float) -> list[list[float]]:
            cosine = math.cos(angle / 2)
            sine = math.sin(angle / 2)
            return [[cosine, -sine], [sine, cosine]]

        identity = [[1.0, 0.0], [0.0, 1.0]]
        bit_flip = [[0.0, 1.0], [1.0, 0.0]]
        for control_state, expected_angle in enumerate(entry_angles):
            realized = identity
            for index, coefficient in enumerate(gray_coefficients):
                realized = multiply(rotation(coefficient), realized)
                transition_bit = (
                    1
                    if index + 1 == len(gray_coefficients)
                    else (
                        evaluator._gray_code(index)
                        ^ evaluator._gray_code(index + 1)
                    ).bit_length()
                    - 1
                )
                if control_state & (1 << transition_bit):
                    realized = multiply(bit_flip, realized)
            expected = rotation(expected_angle)
            for row in range(2):
                for column in range(2):
                    self.assertAlmostEqual(realized[row][column], expected[row][column])

    def test_frozen_workload_hashes_and_source_shell(self) -> None:
        config = evaluator._validated_config()
        workloads = [
            evaluator._build_workload(spec, int(config["matrix_scale"]))
            for spec in config["workloads"]
        ]
        self.assertEqual(len(workloads), 6)
        self.assertTrue(all(workload.sha256 for workload in workloads))
        source = evaluator._validate_candidate_shell(
            evaluator.TASK_DIR / "scripts" / "init.cpp",
            int(config["limits"]["max_candidate_bytes"]),
        )
        self.assertEqual(source, evaluator.BASELINE_PATH.read_bytes())

    def test_baseline_evaluates_to_valid_one(self) -> None:
        metrics, artifacts = evaluator.evaluate(
            evaluator.TASK_DIR / "scripts" / "init.cpp"
        )
        self.assertEqual(metrics["valid"], 1.0)
        self.assertAlmostEqual(metrics["combined_score"], 1.0)
        self.assertEqual(metrics["successful_scenario_count"], 6.0)
        self.assertEqual(metrics["failed_scenario_count"], 0.0)
        self.assertNotIn("failure_summary", artifacts)

    def test_candidate_workload_failure_is_isolated(self) -> None:
        source = (evaluator.TASK_DIR / "scripts" / "init.cpp").read_text(
            encoding="utf-8"
        )
        function_start = "void optimize(Construction &construction) {\n"
        injected_start = function_start + (
            '  if (construction.workload_id() == "polynomial_gram_32")\n'
            '    throw std::runtime_error("intentional isolated failure");\n'
        )
        self.assertIn(function_start, source)
        source = source.replace(function_start, injected_start, 1)

        with tempfile.TemporaryDirectory(prefix="kbe_isolation_test_") as temporary:
            candidate = Path(temporary) / "candidate.cpp"
            candidate.write_text(source, encoding="utf-8")
            metrics, artifacts = evaluator.evaluate(candidate)

        self.assertEqual(metrics["valid"], 0.0)
        self.assertEqual(metrics["combined_score"], 0.0)
        self.assertAlmostEqual(metrics["partial_combined_score"], 1.0)
        self.assertEqual(metrics["successful_scenario_count"], 5.0)
        self.assertEqual(metrics["failed_scenario_count"], 1.0)
        self.assertEqual(
            artifacts["failed_workloads"], ["polynomial_gram_32"]
        )
        failed = artifacts["workloads"]["polynomial_gram_32"]
        self.assertIn("intentional isolated failure", failed["candidate_error"])
        self.assertIn("candidate:", failed["error"])
        self.assertAlmostEqual(
            artifacts["workloads"]["multiscale_rbf_64"]["score"], 1.0
        )


if __name__ == "__main__":
    unittest.main()
