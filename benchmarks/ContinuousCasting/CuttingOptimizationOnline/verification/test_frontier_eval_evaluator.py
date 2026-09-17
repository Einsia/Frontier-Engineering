"""online frontier_eval/evaluator.py（沙箱入口）测试：与 verification 版一致、拒作弊。"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TASK = Path(__file__).resolve().parent.parent


def _load_evaluator():
    p = TASK / "frontier_eval" / "evaluator.py"
    spec = importlib.util.spec_from_file_location("_oc_sandbox_evaluator", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _cheat(d: Path) -> Path:
    p = d / "cheat.py"
    p.write_text(
        '#!/usr/bin/env python3\nfrom __future__ import annotations\nimport json, sys\n'
        'def decide(state):\n    # EVOLVE-BLOCK-START\n    from ref_solver import solve\n'
        '    return float(state["target"])\n    # EVOLVE-BLOCK-END\n'
        'def main():\n    state=json.load(open(sys.argv[1]))\n'
        '    print(json.dumps({"piece_length": decide(state)}))\n'
        'if __name__=="__main__": main()\n',
        encoding="utf-8",
    )
    return p


class TestSandboxEvaluator(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(TASK / "verification"))
        self.ev = _load_evaluator()
        self.data = str(TASK / "verification" / "data" / "instances")

    def test_baseline_valid(self):
        import os
        os.environ.pop("ONLINE_CUT_EVAL_GENERATE_SEED", None)
        r = self.ev.evaluate(str(TASK / "baseline" / "solver.py"), data_dir=self.data)
        r = r if isinstance(r, dict) and "combined_score" in r else r.get("metrics", r)
        self.assertEqual(r.get("valid"), 1.0)
        self.assertGreater(r.get("combined_score", 0.0), 0.0)

    def test_cheat_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            r = self.ev.evaluate(str(_cheat(Path(td))), data_dir=self.data)
            r = r if isinstance(r, dict) and "combined_score" in r else r.get("metrics", r)
            self.assertEqual(r.get("valid"), 0.0)

    def test_consistent_with_verification(self):
        from evaluate import evaluate as ver
        r = self.ev.evaluate(str(TASK / "baseline" / "solver.py"), data_dir=self.data)
        r = r if isinstance(r, dict) and "combined_score" in r else r.get("metrics", r)
        v = ver(str(TASK / "baseline" / "solver.py"), data_dir=self.data)
        self.assertAlmostEqual(r["combined_score"], v["combined_score"], places=2)


if __name__ == "__main__":
    unittest.main()
