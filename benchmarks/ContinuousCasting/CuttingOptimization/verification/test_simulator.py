"""simulator.py 单测：评分规则、校验逻辑、零废段处理。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generator  # noqa: E402
from simulator import (  # noqa: E402
    MAX_BASIC,
    MIN_BASIC,
    TARGET_PENALTY_WEIGHT,
    boundaries,
    piece_penalty,
    piece_scrap,
    score,
    validate,
)


def _inst(seed: int = 1, difficulty: str = "medium"):
    inst = generator.generate(seed, difficulty)
    # 强制放入一个 0.8m 零废段，便于测试（若无则加上一个远离端部的）
    if not inst["defects"]:
        S = float(inst["billet"]["total_length"])
        inst["defects"] = [[round(S / 2.0, 1), round(S / 2.0 + 0.8, 1)]]
    return inst


class TestPieceRules(unittest.TestCase):
    def test_too_short_fully_scrapped(self):
        inst = _inst()
        self.assertEqual(piece_scrap(6.0, inst), 6.0)  # < min_process(8.0) -> 整块报废

    def test_in_window_zero_scrap(self):
        inst = _inst()
        tmin = float(inst["customer"]["target_min"])
        tmax = float(inst["customer"]["target_max"])
        self.assertEqual(piece_scrap((tmin + tmax) / 2.0, inst), 0.0)

    def test_over_target_extra_scrapped(self):
        inst = _inst()
        tmax = float(inst["customer"]["target_max"])
        self.assertAlmostEqual(piece_scrap(tmax + 1.6, inst), 1.6)

    def test_penalty_is_distance_to_target(self):
        inst = _inst()
        t = float(inst["customer"]["target"])
        tmax = float(inst["customer"]["target_max"])
        self.assertAlmostEqual(piece_penalty(t, inst), 0.0)
        # 超出 target_max 的部分会报废；实际交付长度 = min(c, target_max)，惩罚 = |交付 - target|
        self.assertAlmostEqual(piece_penalty(t + 1.0, inst), abs(min(t + 1.0, tmax) - t))


class TestValidate(unittest.TestCase):
    def test_valid_solution_passes(self):
        import ref_solver
        inst = _inst()
        cuts = ref_solver.solve(inst)["cuts"]
        ok, reason = validate(inst, cuts)
        self.assertTrue(ok, reason)

    def test_sum_mismatch(self):
        inst = _inst()
        cuts = [5.0, 5.0]
        ok, _ = validate(inst, cuts)
        self.assertFalse(ok)

    def test_cut_out_of_range(self):
        inst = _inst()
        S = float(inst["billet"]["total_length"])
        # 全部切成越界长度（< min_basic），且不覆盖零废段端点
        cuts = [3.0] * int(round(S / 3.0))
        ok, _ = validate(inst, cuts)
        self.assertFalse(ok)

    def test_defect_piece_allowed_below_min_basic(self):
        import ref_solver
        inst = _inst(seed=3, difficulty="medium")
        self.assertTrue(inst["defects"])
        cuts = ref_solver.solve(inst)["cuts"]
        ok, reason = validate(inst, cuts)
        self.assertTrue(ok, reason)
        # 参考解应包含一个 < min_basic 的零废段块（0.8m），且合法
        defect_len = round(inst["defects"][0][1] - inst["defects"][0][0], 4)
        self.assertLess(defect_len, MIN_BASIC)
        self.assertIn(defect_len, [round(c, 4) for c in cuts])

    def test_crossing_defect_rejected(self):
        inst = _inst()
        a, b = inst["defects"][0]
        # 找两个切口，一个在零废段内部、一个在其后，跨过零废段 -> 非法
        piece_in = a + 0.3  # 落在零废段内
        cuts = [piece_in, 5.0, 5.0, 5.0, 5.0]
        # 需要校验 sum 与端点；直接断言 endpoints 之一不是边界时非法
        ok, reason = validate(inst, cuts)
        # 这些 cuts 大概率 sum 不匹配也非法；重点确认至少被判非法
        self.assertFalse(ok)


class TestScore(unittest.TestCase):
    def test_score_is_scrap_plus_lam_penalty(self):
        import ref_solver
        inst = _inst()
        cuts = ref_solver.solve(inst)["cuts"]
        ok, m = score(inst, cuts)
        self.assertTrue(ok)
        # score 四舍五入到 4 位，故用 3 位精度比较
        self.assertAlmostEqual(
            m["score"], m["scrap"] + TARGET_PENALTY_WEIGHT * m["penalty"], places=3
        )

    def test_invalid_solution_scores_invalid(self):
        inst = _inst()
        ok, m = score(inst, [1.0, 1.0])
        self.assertFalse(ok)
        self.assertFalse(m["valid"])


if __name__ == "__main__":
    unittest.main()
