"""online ref_solver.py 单测：全知参考解合法性、确定性、优于朴素基线。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ref_solver  # noqa: E402
from simulator import partition, score  # noqa: E402
import generator  # noqa: E402


class TestRefSolver(unittest.TestCase):
    def test_solution_valid_and_sums(self):
        for seed in (1, 2, 3):
            inst = generator.generate(seed, "medium", 10)
            cuts = ref_solver.solve(inst)["cuts"]
            ok, m = score(inst, cuts)
            self.assertTrue(ok)
            self.assertAlmostEqual(sum(cuts), float(inst["cast"]["total_length"]), places=2)

    def test_deterministic(self):
        inst = generator.generate(1, "hard", 10)
        self.assertEqual(ref_solver.solve(inst), ref_solver.solve(inst))

    def test_beats_naive_baseline(self):
        """全知参考解的利用率应 > 朴素"恒切目标值"基线。"""
        def naive(state):
            return float(state["target"])
        for seed in (1, 2):
            inst = generator.generate(seed, "medium", 10)
            ref_u = ref_solver.best_util(inst)
            ok, m = score(inst, partition(inst, naive))
            base_u = m["util"] if ok else 0.0
            self.assertGreater(ref_u, base_u, f"seed {seed}")


if __name__ == "__main__":
    unittest.main()
