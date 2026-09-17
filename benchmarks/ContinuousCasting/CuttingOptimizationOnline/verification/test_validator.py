"""online validator.py 单测：静态检查、禁引用、绝对路径、硬编码、环境剥离。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validator import candidate_env, static_check_source  # noqa: E402

BASE = Path(__file__).resolve().parent.parent / "baseline" / "solver.py"

TPL = '''#!/usr/bin/env python3
from __future__ import annotations
import json, sys

def decide(state):
    # EVOLVE-BLOCK-START
    return float(state["target"])
    # EVOLVE-BLOCK-END

def main():
    import json as _j
    state = _j.load(open(sys.argv[1]))
    print(_j.dumps({"piece_length": decide(state)}))

if __name__ == "__main__":
    main()
'''


class TestValidator(unittest.TestCase):
    def test_baseline_passes(self):
        self.assertEqual(_check(BASE, BASE), [])

    def test_ref_import_caught(self):
        src = TPL.replace('return float(state["target"])',
                          'from ref_solver import solve\n    return 0.0')
        self.assertTrue(any("ref_solver" in m for m in static_check_source(src)))

    def test_generator_import_caught(self):
        src = TPL.replace('return float(state["target"])', 'import generator\n    return 0.0')
        self.assertTrue(any("generator" in m.lower() for m in static_check_source(src)))

    def test_absolute_path_caught(self):
        src = TPL.replace('return float(state["target"])', 'open("C:\\\\Users\\\\x")')
        self.assertTrue(any("absolute" in m for m in static_check_source(src)))

    def test_missing_markers_caught(self):
        src = TPL.replace("# EVOLVE-BLOCK-START\n    ", "").replace("# EVOLVE-BLOCK-END\n", "")
        self.assertTrue(any("EVOLVE-BLOCK" in m for m in static_check_source(src)))

    def test_env_strips_frontier(self):
        import os
        os.environ["ONLINE_CUT_EVAL_GENERATE_SEED"] = "42"
        os.environ["FRONTIER_EVAL_SOMETHING"] = "x"
        try:
            env = candidate_env()
            self.assertNotIn("ONLINE_CUT_EVAL_GENERATE_SEED", env)
            self.assertNotIn("FRONTIER_EVAL_SOMETHING", env)
        finally:
            os.environ.pop("ONLINE_CUT_EVAL_GENERATE_SEED", None)
            os.environ.pop("FRONTIER_EVAL_SOMETHING", None)


def _check(p, base):
    return static_check_source(p.read_text(encoding="utf-8"), base.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
