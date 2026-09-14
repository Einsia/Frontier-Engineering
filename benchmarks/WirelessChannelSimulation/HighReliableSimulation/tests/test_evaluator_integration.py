from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


class TestHighReliableSimulationEvaluator(unittest.TestCase):
    def test_init_program_can_be_evaluated(self) -> None:
        repo = Path(__file__).resolve().parents[4]
        eval_path = (
            repo
            / "benchmarks"
            / "WirelessChannelSimulation"
            / "HighReliableSimulation"
            / "verification"
            / "evaluator.py"
        )
        program_path = (
            repo
            / "benchmarks"
            / "WirelessChannelSimulation"
            / "HighReliableSimulation"
            / "scripts"
            / "init.py"
        )

        spec = importlib.util.spec_from_file_location("hrs_eval", str(eval_path))
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        result = module.evaluate(str(program_path), repo_root=repo)
        metrics = result.metrics if hasattr(result, "metrics") else result

        required_keys = {
            "combined_score",
            "runtime_s",
            "error_log_ratio",
            "valid",
            "err_rate_log_median",
            "actual_std_median",
            "target_std_attainment_rate",
            "runtime_s_total",
        }
        self.assertTrue(required_keys.issubset(metrics.keys()))
        self.assertGreater(metrics["runtime_s_total"], 0.0)
        self.assertIn(metrics["valid"], (0.0, 1.0))
        if metrics["actual_std_median"] > module.TARGET_STD:
            self.assertEqual(metrics["valid"], 0.0)
            self.assertEqual(metrics["combined_score"], module.INVALID_COMBINED_SCORE)

    def test_candidate_self_report_cannot_fake_valid_score(self) -> None:
        """The trusted sampling loop ignores candidate-reported aggregates."""
        repo = Path(__file__).resolve().parents[4]
        eval_path = (
            repo
            / "benchmarks"
            / "WirelessChannelSimulation"
            / "HighReliableSimulation"
            / "verification"
            / "evaluator.py"
        )

        spec = importlib.util.spec_from_file_location("hrs_eval", str(eval_path))
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        forged = -13.13
        candidate_source = f"""
import sys
from pathlib import Path

sys.path.insert(0, {str(repo)!r})

from benchmarks.WirelessChannelSimulation.HighReliableSimulation.runtime.sampler import (
    BesselSampler,
)


class MySampler(BesselSampler):
    def simulate_variance_controlled(self, **kwargs):
        # Forged: claims a perfect, converged run without doing any work.
        return ({forged}, 0.0, 0.0, 1.0, 0.0, True)
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            program_path = Path(tmpdir) / "candidate.py"
            program_path.write_text(candidate_source, encoding="utf-8")
            result = module.evaluate(str(program_path), repo_root=repo)

        metrics = result.metrics if hasattr(result, "metrics") else result
        self.assertEqual(metrics["trusted_canonical_loop"], 1.0)
        # The forged number never reaches the scorer.
        self.assertNotAlmostEqual(metrics["err_rate_log_median"], forged, places=6)
        # The real run actually happened: full sample budget was consumed.
        self.assertEqual(metrics["actual_samples_median"], float(module.MAX_SAMPLES))


if __name__ == "__main__":
    unittest.main()
