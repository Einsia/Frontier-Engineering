"""Unit tests for verification/simulator.py (stdlib unittest, no third-party deps).

Run from the TelecomBackup task directory:
    python verification/test_simulator.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulator as sim  # noqa: E402


def _tiny() -> dict:
    """1 站 1 电源 1 栅格：手算用例。"""
    return {
        "grid": {"width": 200.0, "height": 200.0, "nx": 1, "ny": 1},
        "sites": [[100.0, 100.0]],
        "groups": [[0]],
        "battery": [10.0],
        "demand": [0.5],
        "pt_dbm": 20.0, "n_exp": 6.0, "threshold": -105.0,
        "coverage_ratio": 0.8, "delta_min": 5.0, "horizon": 8, "site_cap": 60.0,
    }


class TestTinyManual(unittest.TestCase):
    def setUp(self):
        self.inst = _tiny()

    def test_always_on(self):
        # 工作功耗 1.2+2*min(0.5/60,1)=1.2167kW，8 时隙耗电远小于 10kWh -> 撑满 40min
        self.assertEqual(sim.simulate(self.inst, [[[0, 8]]]), 40.0)

    def test_never_on(self):
        # 一开始就关 -> t=0 覆盖 0 < 80% -> 0 分钟
        self.assertEqual(sim.simulate(self.inst, [[]]), 0.0)

    def test_half_horizon(self):
        # 前 4 时隙开、后关 -> 第 5 时隙跌破 -> 20 分钟
        self.assertEqual(sim.simulate(self.inst, [[[0, 4]]]), 20.0)


class TestNormalizeIntervals(unittest.TestCase):
    def test_merge_overlap(self):
        self.assertEqual(sim._normalize_intervals([[0, 10], [5, 15]], 96), [[0, 15]])

    def test_merge_adjacent(self):
        self.assertEqual(sim._normalize_intervals([[0, 5], [5, 10]], 96), [[0, 10]])

    def test_empty_interval_list(self):
        self.assertEqual(sim._normalize_intervals([], 96), [])

    def test_out_of_order(self):
        # 乱序的合法区间：排序后升序返回
        self.assertEqual(sim._normalize_intervals([[3, 8], [0, 2]], 96), [[0, 2], [3, 8]])

    def test_invalid_interval_filtered(self):
        # a >= b 的畸形区间被忽略
        self.assertEqual(sim._normalize_intervals([[8, 3], [0, 2]], 96), [[0, 2]])


class TestBatteryDepletion(unittest.TestCase):
    def test_tiny_battery_dies(self):
        inst = _tiny()
        inst["battery"] = [0.05]  # 1 个时隙都撑不过
        # 全开：第 1 时隙扣电后耗尽停服 -> 覆盖掉到 0 -> 该时隙跌破 -> 0 分钟
        self.assertEqual(sim.simulate(inst, [[[0, 8]]]), 0.0)

    def test_multi_power_some_dead(self):
        inst = {
            "grid": {"width": 200.0, "height": 200.0, "nx": 2, "ny": 2},
            "sites": [[50, 50], [150, 150]],
            "groups": [[0], [1]],
            "battery": [0.05, 20.0],
            "demand": [0.5] * 4,
            "pt_dbm": 20.0, "n_exp": 6.0, "threshold": -105.0,
            "coverage_ratio": 0.4, "delta_min": 5.0, "horizon": 10, "site_cap": 60.0,
        }
        # 电源 0 立即耗尽停服，电源 1 继续服务；覆盖要求 40% 很容易满足 -> 撑满
        self.assertEqual(sim.simulate(inst, [[[0, 10]], [[0, 10]]]), 50.0)


class TestDeterminism(unittest.TestCase):
    def test_same_input_same_output(self):
        inst = _tiny()
        a = sim.simulate(inst, [[[0, 8]]])
        b = sim.simulate(inst, [[[0, 8]]])
        self.assertEqual(a, b)


class TestCoverageConstraint(unittest.TestCase):
    def test_coverage_falls_below_ratio_ends_early(self):
        inst = _tiny()
        inst["coverage_ratio"] = 0.9  # 单站时覆盖不足，需两站才满足
        inst["sites"] = [[50, 50], [150, 150]]
        inst["groups"] = [[0], [1]]
        inst["battery"] = [20.0, 20.0]
        inst["demand"] = [0.5] * 4  # 与 2x2 栅格匹配
        inst["grid"] = {"width": 200.0, "height": 200.0, "nx": 2, "ny": 2}
        # 只开电源 0：(150,150) 栅格无良好覆盖 -> 良好 3/4=75% < 90% -> t=0 跌破 -> 0 分钟
        self.assertEqual(sim.simulate(inst, [[[0, 8]], []]), 0.0)
        # 两个都开 -> 覆盖 4/4=100% >= 90% -> 撑满 8 时隙（horizon=8）= 40 分钟
        self.assertEqual(sim.simulate(inst, [[[0, 8]], [[0, 8]]]), 40.0)


if __name__ == "__main__":
    unittest.main()
