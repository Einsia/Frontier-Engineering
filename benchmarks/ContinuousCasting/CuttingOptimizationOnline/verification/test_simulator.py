"""online simulator.py 单测：评分合法性与校验规则。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generator  # noqa: E402
import ref_solver  # noqa: E402
from simulator import partition, score  # noqa: E402


def _inst(seed: int = 1, reveal: float = 10.0, diff: str = "medium"):
    return generator.generate(seed, diff, reveal)


def _decide(state):
    return float(state["target"])


class TestScore(unittest.TestCase):
    def test_ref_solution_scores_valid(self):
        for seed in (1, 2, 3):
            inst = _inst(seed)
            cuts = ref_solver.solve(inst)["cuts"]
            ok, m = score(inst, cuts)
            self.assertTrue(ok, f"seed {seed}")
            self.assertGreaterEqual(m["scrap"], 0.0)
            self.assertGreaterEqual(m["util"], 0.0)
            self.assertLessEqual(m["util"], 100.0)

    def test_short_tail_scrapped_not_invalid(self):
        # 手搓小实例：最后一段 <4.8 视为报废，不判非法
        inst = {"seed": 0,
                "process": {"v": 1.0, "tc": 3, "tr": 1, "buffer_len": 60.0,
                            "scrap_len": 0.8, "reveal_lead": 10.0},
                "cast": {"total_length": 20.0, "t_cast": 140.0},
                "customer": {"target": 9.0, "target_min": 8.5, "target_max": 9.5},
                "limits": {"min_basic": 4.8, "max_basic": 12.6,
                           "min_process": 8.0, "max_process": 11.6},
                "defects": []}
        cuts = [8.0, 8.0, 4.0]  # 尾段 4.0 < 4.8
        ok, m = score(inst, cuts)
        self.assertTrue(ok)
        # 尾段 4.0 报废；8.0 在 [min_process, target_min) 内 -> 0 报废
        self.assertAlmostEqual(m["scrap"], 4.0, places=2)


class TestPartition(unittest.TestCase):
    def test_partition_sums_to_total(self):
        inst = _inst(2, 10)
        cuts = partition(inst, _decide)
        self.assertAlmostEqual(sum(cuts), float(inst["cast"]["total_length"]), places=2)

    def test_partition_intermediate_in_window(self):
        inst = _inst(3, 10)
        cuts = partition(inst, _decide)
        lo = inst["limits"]["min_basic"]
        for c in cuts[:-1]:
            self.assertGreaterEqual(c, lo - 1e-3)


if __name__ == "__main__":
    unittest.main()
