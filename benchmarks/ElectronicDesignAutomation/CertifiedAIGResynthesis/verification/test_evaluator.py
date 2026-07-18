"""Regression tests for the certified AIG resynthesis evaluator."""

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


class CertifiedAigEvaluatorTests(unittest.TestCase):
    def _candidate_with_optimize_body(self, body: str) -> str:
        source = (evaluator.TASK_DIR / "scripts" / "init.cpp").read_text(
            encoding="utf-8"
        )
        start = source.index("void optimize(Optimizer& optimizer) {")
        opening_brace = source.index("{", start)
        depth = 1
        cursor = opening_brace + 1
        while depth:
            if source[cursor] == "{":
                depth += 1
            elif source[cursor] == "}":
                depth -= 1
            cursor += 1
        replacement = "void optimize(Optimizer& optimizer) {\n" + body + "\n}"
        return source[:start] + replacement + source[cursor:]

    def _evaluate_source(
        self, source: str, *, timeout_s: float | None = None
    ) -> tuple[dict[str, float], dict[str, object]]:
        with tempfile.TemporaryDirectory(prefix="certified_aig_test_") as temporary:
            candidate = Path(temporary) / "candidate.cpp"
            candidate.write_text(source, encoding="utf-8")
            return evaluator.evaluate(candidate, timeout_override_s=timeout_s)

    def test_baseline_evaluates_to_valid_one(self) -> None:
        metrics, artifacts = evaluator.evaluate(
            evaluator.TASK_DIR / "scripts" / "init.cpp"
        )

        self.assertEqual(metrics["valid"], 1.0)
        self.assertAlmostEqual(metrics["combined_score"], 1.0)
        self.assertEqual(metrics["successful_scenario_count"], 5.0)
        self.assertEqual(metrics["failed_scenario_count"], 0.0)
        self.assertNotIn("failure_summary", artifacts)
        self.assertTrue(
            all(result["status"] == "ok" for result in artifacts["workloads"].values())
        )

    def test_evolve_block_boundary_violation_is_rejected(self) -> None:
        source = (evaluator.TASK_DIR / "scripts" / "init.cpp").read_text(
            encoding="utf-8"
        )
        metrics, artifacts = self._evaluate_source("// forbidden shell edit\n" + source)

        self.assertEqual(metrics["valid"], 0.0)
        self.assertEqual(metrics["combined_score"], 0.0)
        self.assertIn("outside the EVOLVE block", artifacts["error_message"])
        self.assertNotIn("compile", artifacts)

    def test_checker_rejects_wrong_truth_table_and_local_cycle(self) -> None:
        config = evaluator._validated_config()
        aag = b"aag 3 2 0 1 1\n2\n4\n6\n6 2 4\n"

        with self.assertRaisesRegex(evaluator.EvaluationError, "truth table"):
            evaluator.ProofChecker(aag, config["limits"]).replay(
                b"CERT1\nR 3 2 0 0 1 2 2\n"
            )
        with self.assertRaisesRegex(evaluator.EvaluationError, "forward"):
            evaluator.ProofChecker(aag, config["limits"]).replay(
                b"CERT1\nR 3 2 0 1 1 2 6 2 6\n"
            )

    def test_candidate_crash_is_isolated_to_one_workload(self) -> None:
        source = self._candidate_with_optimize_body(
            "  if (optimizer.input_count() == 128U)\n"
            '    throw std::runtime_error("intentional isolated crash");'
        )
        metrics, artifacts = self._evaluate_source(source)

        failed_id = "priority_arbiter_128"
        self.assertEqual(metrics["valid"], 0.0)
        self.assertEqual(metrics["combined_score"], 0.0)
        self.assertGreater(metrics["partial_combined_score"], 0.0)
        self.assertEqual(metrics["successful_scenario_count"], 4.0)
        self.assertEqual(metrics["failed_scenario_count"], 1.0)
        self.assertEqual(artifacts["failed_workloads"], [failed_id])
        failed = artifacts["workloads"][failed_id]
        self.assertIn("intentional isolated crash", failed["candidate_error"])
        self.assertEqual(artifacts["workloads"]["packet_classifier_48x12"]["status"], "ok")
        self.assertEqual(artifacts["workloads"]["crc32_update_64"]["status"], "ok")

    def test_candidate_timeouts_are_reported_and_isolated(self) -> None:
        source = self._candidate_with_optimize_body(
            "  volatile std::uint64_t spin = 0;\n"
            "  while (optimizer.node_count() > 0U) ++spin;"
        )
        metrics, artifacts = self._evaluate_source(source, timeout_s=0.25)

        self.assertEqual(metrics["valid"], 0.0)
        self.assertEqual(metrics["combined_score"], 0.0)
        self.assertEqual(metrics["timeout"], 1.0)
        self.assertEqual(metrics["successful_scenario_count"], 0.0)
        self.assertEqual(metrics["failed_scenario_count"], 5.0)
        self.assertEqual(len(artifacts["failed_workloads"]), 5)
        self.assertTrue(
            all(
                "timed out" in result["candidate_error"]
                for result in artifacts["workloads"].values()
            )
        )

    @unittest.skipUnless(
        hasattr(evaluator.resource, "RLIMIT_NPROC"), "RLIMIT_NPROC is unavailable"
    )
    def test_process_limit_is_applied(self) -> None:
        with mock.patch.object(evaluator.resource, "setrlimit") as setrlimit:
            evaluator._resource_limits(4.0, 16_000_000, 64)
        setrlimit.assert_any_call(evaluator.resource.RLIMIT_NPROC, (64, 64))

    def test_workload_ids_and_descriptions_are_readable(self) -> None:
        config = evaluator._validated_config()
        for workload in config["workloads"]:
            self.assertIn("_", workload["id"])
            self.assertTrue(str(workload.get("description", "")).strip())


if __name__ == "__main__":
    unittest.main()
