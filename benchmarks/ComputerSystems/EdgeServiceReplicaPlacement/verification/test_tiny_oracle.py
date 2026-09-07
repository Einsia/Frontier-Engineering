from __future__ import annotations

import unittest

from evaluator import evaluate_action_sequence
from tiny_oracle import TINY_CONFIG, TINY_SCENARIO, brute_force_oracle


class MultiTimestepTinyOracleTests(unittest.TestCase):
    def test_bruteforce_oracle_matches_production_simulator_and_score_exactly(self) -> None:
        oracle = brute_force_oracle()
        evaluated = evaluate_action_sequence(
            oracle["best_action_sequence"], TINY_SCENARIO, TINY_CONFIG
        )
        self.assertEqual(oracle["raw_metrics"], evaluated["raw_metrics"])
        self.assertEqual(oracle["normalized_loss_components"], evaluated["normalized_loss_components"])
        self.assertEqual(oracle["combined_score"], evaluated["combined_score"])


if __name__ == "__main__":
    unittest.main()
