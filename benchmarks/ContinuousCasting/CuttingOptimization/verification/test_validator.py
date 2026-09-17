"""validator.py 单测：静态完整性检查、禁引用、绝对路径、硬编码、环境剥离。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validator import (  # noqa: E402
    candidate_env,
    check_candidate,
    static_check_source,
)

BASELINE = Path(__file__).resolve().parent.parent / "baseline" / "solver.py"

TEMPLATE = '''#!/usr/bin/env python3
"""candidate"""
from __future__ import annotations
import json, sys
from pathlib import Path

def solve(inst):
    # EVOLVE-BLOCK-START
    return [float(inst['billet']['total_length'])]
    # EVOLVE-BLOCK-END
'''

CHEAT_REF = TEMPLATE.replace('return [float(inst[\'billet\'][\'total_length\'])]', 'from ref_solver import solve\n    return solve(inst)["cuts"]')
CHEAT_GEN = TEMPLATE.replace('return [float(inst[\'billet\'][\'total_length\'])]', 'import generator\n    return generator.generate(1)["billet"]')
CHEAT_ABS = TEMPLATE.replace('return [float(inst[\'billet\'][\'total_length\'])]', 'open("C:\\\\Users\\\\x.txt")')
CHEAT_HARDCODE = TEMPLATE.replace('return [float(inst[\'billet\'][\'total_length\'])]', 'return [("instance_1": [1,2])]')
NO_MARKERS = TEMPLATE.replace('# EVOLVE-BLOCK-START\n    ', '').replace('# EVOLVE-BLOCK-END\n', '')


class TestValidator(unittest.TestCase):
    def test_baseline_passes(self):
        self.assertEqual(check_candidate(BASELINE, baseline_path=BASELINE), [])

    def test_plain_candidate_passes(self):
        self.assertEqual(static_check_source(TEMPLATE), [])

    def test_ref_solver_import_caught(self):
        self.assertTrue(any("ref_solver" in m for m in static_check_source(CHEAT_REF)))

    def test_generator_import_caught(self):
        self.assertTrue(any("generator" in m.lower() for m in static_check_source(CHEAT_GEN)))

    def test_absolute_path_caught(self):
        self.assertTrue(any("absolute" in m for m in static_check_source(CHEAT_ABS)))

    def test_hardcode_caught(self):
        self.assertTrue(any("hardcode" in m.lower() for m in static_check_source(CHEAT_HARDCODE)))

    def test_missing_markers_caught(self):
        self.assertTrue(any("EVOLVE-BLOCK" in m for m in static_check_source(NO_MARKERS)))

    def test_fixed_region_vs_baseline(self):
        # 修改了 EVOLVE-BLOCK 之外的代码（改 docstring）应被抓到
        base_src = BASELINE.read_text(encoding="utf-8")
        mod = base_src.replace("朴素基线", "朴素基线（被修改）").replace("连铸切割 baseline 求解器", "连铸切割 baseline 求解器X")
        self.assertTrue(any("outside EVOLVE-BLOCK" in m for m in static_check_source(mod, base_src)))

    def test_candidate_env_strips_vars(self):
        import os
        os.environ["CUTTING_EVAL_GENERATE_SEED"] = "42"
        os.environ["FRONTIER_EVAL_SOMETHING"] = "x"
        try:
            env = candidate_env()
            self.assertNotIn("CUTTING_EVAL_GENERATE_SEED", env)
            self.assertNotIn("FRONTIER_EVAL_SOMETHING", env)
        finally:
            os.environ.pop("CUTTING_EVAL_GENERATE_SEED", None)
            os.environ.pop("FRONTIER_EVAL_SOMETHING", None)


if __name__ == "__main__":
    unittest.main()
