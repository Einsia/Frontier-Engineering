from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_evaluator():
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
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return repo, module


def _metrics(result):
    return result.metrics if hasattr(result, "metrics") else result


class TestHighReliableSimulationEvaluator(unittest.TestCase):
    def test_init_program_can_be_evaluated(self) -> None:
        repo, module = _load_evaluator()
        program_path = (
            repo
            / "benchmarks"
            / "WirelessChannelSimulation"
            / "HighReliableSimulation"
            / "scripts"
            / "init.py"
        )

        result = module.evaluate(str(program_path), repo_root=repo)
        metrics = _metrics(result)

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
        # The candidate is executed in a subprocess, never in this process.
        self.assertEqual(metrics["isolated_candidate"], 1.0)
        if metrics["actual_std_median"] > module.TARGET_STD:
            self.assertEqual(metrics["valid"], 0.0)
            self.assertEqual(metrics["combined_score"], module.INVALID_COMBINED_SCORE)

    def test_candidate_self_report_cannot_fake_valid_score(self) -> None:
        """A candidate's own simulate_variance_controlled() is never consulted.

        The benchmark-owned loop drives the candidate's sample(); anything the
        candidate reports about its own aggregate result is ignored. This used to
        be checked by patching an evaluator internal -- it is now a structural
        property, so it is checked end to end.
        """
        repo, module = _load_evaluator()

        # -13.13 is far enough from R0_LOG_DEV (~-14.135) that, if it were
        # believed, err_log_ratio would exceed EPSILON and valid would be 0.
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

        metrics = _metrics(result)
        self.assertEqual(metrics["trusted_canonical_loop"], 1.0)
        # The forged number never reaches the scorer.
        self.assertNotAlmostEqual(metrics["err_rate_log_median"], forged, places=6)
        # The real run actually happened: full sample budget was consumed.
        self.assertEqual(metrics["actual_samples_median"], float(module.MAX_SAMPLES))

    def test_candidate_cannot_patch_the_scorer(self) -> None:
        """Module-level code in the candidate cannot reach the scoring process.

        The candidate below rebinds numpy.median to a constant at import time.
        Under the old in-process ``runpy.run_path`` this would have corrupted
        every median the evaluator computes. Now it only affects the subprocess.
        """
        repo, module = _load_evaluator()

        candidate_source = f"""
import sys
from pathlib import Path

sys.path.insert(0, {str(repo)!r})

import numpy

# Hostile module-level side effect: poison the aggregation the scorer uses.
numpy.median = lambda *a, **k: 12345.0
numpy.nanmedian = lambda *a, **k: 12345.0
numpy.mean = lambda *a, **k: 12345.0

from benchmarks.WirelessChannelSimulation.HighReliableSimulation.runtime.sampler import (
    BesselSampler,
)


class MySampler(BesselSampler):
    pass
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            program_path = Path(tmpdir) / "candidate.py"
            program_path.write_text(candidate_source, encoding="utf-8")
            result = module.evaluate(str(program_path), repo_root=repo)

        metrics = _metrics(result)
        for key in ("err_rate_log_median", "actual_std_median", "converged_rate"):
            self.assertNotEqual(metrics[key], 12345.0, msg=f"{key} was poisoned")

        # numpy in *this* process is untouched.
        import numpy as np

        self.assertEqual(float(np.median([1.0, 2.0, 3.0])), 2.0)


if __name__ == "__main__":
    unittest.main()
