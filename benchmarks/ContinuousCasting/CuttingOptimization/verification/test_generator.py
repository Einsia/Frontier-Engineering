"""generator.py 单测：确定性、零废段约束、干净坯段可行性、interesting 验收。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generator  # noqa: E402
from simulator import MIN_BASIC  # noqa: E402


class TestGenerate(unittest.TestCase):
    def test_deterministic_same_seed(self):
        a = generator.generate(123, "medium")
        b = generator.generate(123, "medium")
        self.assertEqual(a, b)

    def test_lengths_are_grid_multiples(self):
        """所有长度均应接近 0.1 的整数倍（0.02 网格可整除，保证 DP 无舍入误差）。"""
        inst = generator.generate(7, "hard")
        S = float(inst["billet"]["total_length"])
        self.assertAlmostEqual(round(S / 0.02) * 0.02, S, places=6)
        for a, b in inst["defects"]:
            self.assertEqual(abs((b - a) - 0.8) < 1e-6, True)

    def test_defects_within_bounds_and_sorted(self):
        inst = generator.generate(6, "hard")
        S = float(inst["billet"]["total_length"])
        prev_end = 0.0
        for a, b in inst["defects"]:
            self.assertGreaterEqual(a, 0.0)
            self.assertLessEqual(b, S)
            self.assertGreater(a, prev_end)
            self.assertGreaterEqual(a - prev_end, MIN_BASIC - 1e-6)
            prev_end = b
        self.assertGreaterEqual(S - prev_end, MIN_BASIC - 1e-6)

    def test_clean_segments_all_feasible(self):
        inst = generator.generate(5, "medium")
        segs = generator.clean_segments(inst)
        self.assertTrue(segs)
        for _s, length in segs:
            self.assertGreaterEqual(length, MIN_BASIC - 1e-6)

    def test_interesting_ok_on_accepted_instances(self):
        """main() 产出的每个实例都应通过 _interesting_ok（有 headroom、非退化）。"""
        for p in sorted(Path(__file__).parent.glob("data/instances/instance_*.json")):
            import json
            inst = json.loads(p.read_text(encoding="utf-8"))
            self.assertTrue(generator._interesting_ok(inst), p.name)


if __name__ == "__main__":
    unittest.main()
