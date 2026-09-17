from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from evaluator import evaluate, scenario_score


ROOT = Path(__file__).resolve().parents[1]


class EvaluatorTests(unittest.TestCase):
    def test_tail_latency_component_is_continuous_below_slo_reference(self) -> None:
        metrics = {
            "unserved_rate": 0.0,
            "p99_slo_violation_rate": 0.0,
            "request_weighted_p99_ms": 45.0,
            "compute_cost": 0.0,
            "cross_region_gb": 0.0,
            "failure_recovery_steps": 0.0,
        }
        _, components = scenario_score(metrics)
        self.assertEqual(components["tail_latency"], 0.25)

    def test_calibration_policies_are_valid_and_distinguishable(self) -> None:
        weak = evaluate(ROOT / "calibration" / "weak.py")
        reasonable = evaluate(ROOT / "scripts" / "init.py")
        strong = evaluate(ROOT / "calibration" / "strong.py")
        results = (weak, reasonable, strong)
        self.assertTrue(all(result["valid"] == 1.0 for result in results))
        scores = [float(result["combined_score"]) for result in results]
        self.assertEqual(len(set(scores)), 3)
        self.assertGreater(max(scores) - min(scores), 0.25)

    def test_reasonable_baseline_is_deterministic(self) -> None:
        first = evaluate(ROOT / "scripts" / "init.py")
        second = evaluate(ROOT / "scripts" / "init.py")
        self.assertEqual(first, second)
        self.assertEqual(first["valid"], 1.0)

    def test_invalid_action_cannot_compete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "invalid.py"
            candidate.write_text(
                "def decide(observation):\n"
                "    return {'replicas': [{'service_id': 'api', 'node_id': 'a-1', 'count': True}], 'routes': []}\n",
                encoding="utf-8",
            )
            result = evaluate(candidate)
        self.assertEqual(result["valid"], 0.0)
        self.assertEqual(result["combined_score"], 0.0)
        self.assertIn("type", result["rows"][0]["error"])


if __name__ == "__main__":
    unittest.main()
