"""evaluate.py 单测：完整评测链路（baseline 合法 + 作弊候选被拒绝 + 运行时生成）。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evaluate  # noqa: E402

BASELINE = Path(__file__).resolve().parent.parent / "baseline" / "solver.py"

CHEAT = '''#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path

def solve(inst):
    # EVOLVE-BLOCK-START
    from ref_solver import solve as ref
    return ref(inst)["cuts"]
    # EVOLVE-BLOCK-END
'''


class TestEvaluator(unittest.TestCase):
    def test_baseline_scores_positive_and_valid(self):
        res = evaluate.evaluate(str(BASELINE), time_budget=20)
        self.assertEqual(res["valid"], 1.0)
        self.assertGreater(res["combined_score"], 0.0)
        self.assertGreater(res["num_instances"], 0)

    def test_runtime_generation_adds_instances(self):
        import os
        os.environ["CUTTING_EVAL_GENERATE_SEED"] = "7"
        os.environ["CUTTING_EVAL_GENERATE_COUNT"] = "3"
        try:
            res = evaluate.evaluate(str(BASELINE), time_budget=20)
        finally:
            del os.environ["CUTTING_EVAL_GENERATE_SEED"]
            del os.environ["CUTTING_EVAL_GENERATE_COUNT"]
        gen = [k for k in res["per_instance"] if k.startswith("gen_")]
        self.assertEqual(len(gen), 3)

    def test_cheating_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            cheat = Path(td) / "cheat.py"
            cheat.write_text(CHEAT, encoding="utf-8")
            res = evaluate.evaluate(str(cheat), time_budget=20,
                                    data_dir=Path(__file__).parent / "data" / "instances")
            self.assertEqual(res["valid"], 0.0)
            # 所有实例都应 preflight_failed（或至少 combined_score 为 0）
            self.assertLessEqual(res["combined_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
