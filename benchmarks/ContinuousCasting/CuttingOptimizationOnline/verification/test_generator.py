"""online generator.py 单测：确定性、隐藏异常、可驱动性。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generator  # noqa: E402


class TestGenerate(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(generator.generate(7, "medium", 10), generator.generate(7, "medium", 10))

    def test_reveal_lead_set(self):
        for rl in (10.0, 60.0):
            inst = generator.generate(1, "medium", rl)
            self.assertEqual(inst["process"]["reveal_lead"], rl)

    def test_defects_within_bounds_and_sorted(self):
        inst = generator.generate(6, "hard", 10)
        S = float(inst["cast"]["total_length"])
        prev = 0.0
        for a, b in inst["defects"]:
            self.assertGreater(a, prev)
            self.assertGreaterEqual(a, inst["limits"]["min_basic"] - 1e-6)
            self.assertLessEqual(b, S)
            prev = b

    def test_strip_for_agent_hides_defects(self):
        inst = generator.generate(3, "medium", 10)
        ag = generator.strip_for_agent(inst)
        self.assertNotIn("defects", ag)
        self.assertNotIn("anomaly_seed", ag)


if __name__ == "__main__":
    unittest.main()
