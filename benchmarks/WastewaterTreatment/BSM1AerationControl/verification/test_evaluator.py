from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

try:
    from verification.bsm1_model import load_config
    from verification.evaluator import evaluate, simulate_scenario, validate_action
except ModuleNotFoundError:
    from bsm1_model import load_config
    from evaluator import evaluate, simulate_scenario, validate_action


BASELINE_ACTION = {
    "kla3_per_day": 240.0,
    "kla4_per_day": 240.0,
    "kla5_per_day": 84.0,
    "internal_recycle_m3_per_day": 55338.0,
}


class EvaluatorTests(unittest.TestCase):
    def _candidate(self, source: str) -> Path:
        directory = tempfile.TemporaryDirectory(prefix="bsm1_candidate_test_")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "candidate.py"
        path.write_text(source, encoding="utf-8")
        return path

    def test_action_schema_type_range_and_slew_are_enforced(self) -> None:
        config = load_config()
        self.assertEqual(validate_action(dict(BASELINE_ACTION), BASELINE_ACTION, config), BASELINE_ACTION)
        invalid_actions: list[dict[str, Any]] = [
            {key: value for key, value in BASELINE_ACTION.items() if key != "kla5_per_day"},
            dict(BASELINE_ACTION, kla3_per_day=True),
            dict(BASELINE_ACTION, kla3_per_day=361.0),
            dict(BASELINE_ACTION, internal_recycle_m3_per_day=1000.0),
        ]
        for action in invalid_actions:
            with self.subTest(action=action), self.assertRaises((TypeError, ValueError)):
                validate_action(action, BASELINE_ACTION, config)

    def test_lower_recycle_exposes_measurable_optimization_headroom(self) -> None:
        scenario = {"scenario_id": "dry", "weather": "dry"}
        lower_recycle = dict(BASELINE_ACTION, internal_recycle_m3_per_day=30000.0)
        reset = lambda _: None
        baseline = simulate_scenario(
            scenario, lambda _: BASELINE_ACTION, reset, max_steps=96
        )
        improved = simulate_scenario(
            scenario, lambda _: lower_recycle, reset, max_steps=96
        )
        self.assertGreater(improved["score"], baseline["score"] + 0.5)
        self.assertLess(
            improved["metrics"]["pumping_energy_kwh_per_day"],
            baseline["metrics"]["pumping_energy_kwh_per_day"],
        )

    def test_short_baseline_evaluation_is_valid_and_deterministic(self) -> None:
        source = (
            "def reset_controller(scenario): pass\n"
            f"def control(observation): return {BASELINE_ACTION!r}\n"
        )
        candidate = self._candidate(source)
        first = evaluate(candidate, max_steps=2)
        second = evaluate(candidate, max_steps=2)
        self.assertEqual(first, second)
        self.assertEqual(first["valid"], 1.0)
        self.assertEqual(first["completed_scenarios"], 3.0)

    def test_malformed_candidate_returns_zero_instead_of_crashing(self) -> None:
        result = evaluate(self._candidate("def broken(:\n"), max_steps=2)
        self.assertEqual(result["valid"], 0.0)
        self.assertEqual(result["combined_score"], 0.0)
        self.assertIn("candidate import failed", result["error"])


if __name__ == "__main__":
    unittest.main()
