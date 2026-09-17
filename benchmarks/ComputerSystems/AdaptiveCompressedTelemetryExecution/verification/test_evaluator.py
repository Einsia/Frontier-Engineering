"""Regression tests for the adaptive telemetry evaluator."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


VERIFICATION_DIR = Path(__file__).resolve().parent
if str(VERIFICATION_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFICATION_DIR))

import evaluator  # noqa: E402


class AdaptiveTelemetryEvaluatorTests(unittest.TestCase):
    def test_baseline_encode_decode_and_query_pipeline(self) -> None:
        metrics, artifacts = evaluator.evaluate(
            evaluator.TASK_DIR / "scripts" / "init.cpp"
        )

        self.assertEqual(metrics["valid"], 1.0)
        self.assertAlmostEqual(metrics["combined_score"], 1.0)
        self.assertEqual(metrics["successful_scenario_count"], 3.0)
        self.assertEqual(metrics["failed_scenario_count"], 0.0)
        self.assertNotIn("failure_summary", artifacts)
        for result in artifacts["scenario_results"].values():
            self.assertEqual(result["status"], "ok")
            self.assertEqual(
                set(result["candidate"]["measurements"]),
                {"encode", "decode", "query"},
            )
            self.assertEqual(
                set(result["query_expected"]),
                {
                    "error_count",
                    "error_payload",
                    "hot_service_count",
                    "hot_service_duration",
                    "low_service_duration",
                    "middle_latency_count",
                    "middle_window_count",
                    "window_payload",
                },
            )

    def test_evolve_block_boundary_violation_is_rejected(self) -> None:
        source = (evaluator.TASK_DIR / "scripts" / "init.cpp").read_text(
            encoding="utf-8"
        )
        with tempfile.TemporaryDirectory(prefix="telemetry_shell_test_") as temporary:
            candidate = Path(temporary) / "candidate.cpp"
            candidate.write_text("// forbidden shell edit\n" + source, encoding="utf-8")
            metrics, artifacts = evaluator.evaluate(candidate)

        self.assertEqual(metrics["valid"], 0.0)
        self.assertEqual(metrics["combined_score"], 0.0)
        self.assertIn("outside the EVOLVE block", artifacts["error_message"])
        self.assertNotIn("candidate_compile", artifacts)

    def test_candidate_scenario_failure_is_isolated(self) -> None:
        problem, _execution, _pricing, scenarios = evaluator._load_problem()
        evaluation_seed = int(problem["evaluation_seed"])
        failed_scenario = scenarios[1]
        columns = evaluator._generate_columns(failed_scenario, evaluation_seed)
        sentinel_timestamp = int(columns[0][0])

        source = (evaluator.TASK_DIR / "scripts" / "init.cpp").read_text(
            encoding="utf-8"
        )
        function_start = (
            "bool encode_block(const BlockView &input, "
            "std::vector<std::uint8_t> &encoded) {\n"
        )
        injected_start = function_start + (
            "  if (input.count != 0 && input.columns[0][0] == "
            f"{sentinel_timestamp}ULL) return false;\n"
        )
        self.assertIn(function_start, source)
        source = source.replace(function_start, injected_start, 1)

        with tempfile.TemporaryDirectory(prefix="telemetry_isolation_test_") as temporary:
            candidate = Path(temporary) / "candidate.cpp"
            candidate.write_text(source, encoding="utf-8")
            metrics, artifacts = evaluator.evaluate(candidate)

        failed_id = str(failed_scenario["id"])
        self.assertEqual(metrics["valid"], 0.0)
        self.assertEqual(metrics["combined_score"], 0.0)
        self.assertGreater(metrics["partial_combined_score"], 0.0)
        self.assertEqual(metrics["successful_scenario_count"], 2.0)
        self.assertEqual(metrics["failed_scenario_count"], 1.0)
        self.assertEqual(artifacts["failed_scenarios"], [failed_id])
        failed = artifacts["scenario_results"][failed_id]
        self.assertIn("encode_block returned false", failed["candidate_error"])
        self.assertIn("candidate:", failed["error"])
        self.assertEqual(
            artifacts["scenario_results"]["incident_distribution_shift"]["status"],
            "ok",
        )

    @unittest.skipUnless(
        hasattr(evaluator.resource, "RLIMIT_NPROC"), "RLIMIT_NPROC is unavailable"
    )
    def test_process_limit_is_applied(self) -> None:
        with mock.patch.object(evaluator.resource, "setrlimit") as setrlimit:
            evaluator._preexec_limits(1024, 64, None, 30)()
        setrlimit.assert_any_call(evaluator.resource.RLIMIT_NPROC, (64, 64))


if __name__ == "__main__":
    unittest.main()
