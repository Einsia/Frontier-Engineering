"""online evaluate.py 单测：闭环驱动、作弊拒绝、运行时生成。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evaluate  # noqa: E402

BASE = Path(__file__).resolve().parent.parent / "baseline" / "solver.py"
DATA = Path(__file__).resolve().parent / "data" / "instances"

CHEAT = '''#!/usr/bin/env python3
from __future__ import annotations
import json, sys

def decide(state):
    # EVOLVE-BLOCK-START
    from ref_solver import solve, best_util
    return float(state["target"])
    # EVOLVE-BLOCK-END

def main():
    state = json.load(open(sys.argv[1]))
    print(json.dumps({"piece_length": decide(state)}))

if __name__ == "__main__":
    main()
'''


class TestEvaluator(unittest.TestCase):
    def test_baseline_valid(self):
        res = evaluate.evaluate(str(BASE), time_budget=30, data_dir=str(DATA))
        self.assertEqual(res["valid"], 1.0)
        self.assertGreater(res["combined_score"], 0.0)

    def test_cheat_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            c = Path(td) / "cheat.py"
            c.write_text(CHEAT, encoding="utf-8")
            res = evaluate.evaluate(str(c), time_budget=30, data_dir=str(DATA))
            self.assertEqual(res["valid"], 0.0)

    def test_runtime_generation(self):
        import os
        os.environ["ONLINE_CUT_EVAL_GENERATE_SEED"] = "7"
        os.environ["ONLINE_CUT_EVAL_GENERATE_COUNT"] = "3"
        try:
            res = evaluate.evaluate(str(BASE), time_budget=30, data_dir=str(DATA))
        finally:
            os.environ.pop("ONLINE_CUT_EVAL_GENERATE_SEED", None)
            os.environ.pop("ONLINE_CUT_EVAL_GENERATE_COUNT", None)
        gen = [k for k in res["per_instance"] if k.startswith("gen_")]
        self.assertEqual(len(gen), 3)


if __name__ == "__main__":
    unittest.main()
