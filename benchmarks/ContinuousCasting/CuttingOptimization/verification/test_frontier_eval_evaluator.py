"""frontier_eval/evaluator.py（沙箱入口）测试。

对齐 CVRP 评审点："沙箱版 evaluator 必须有测试覆盖"——测试 benchmark 的 uniform 入口
（run_eval 加载的 evaluator.py）与 verification/evaluate.py 行为一致，且能拒绝作弊候选。
"""

from __future__ import annotations

import importlib.util
import json
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


def _write_cheat(d: Path) -> Path:
    """作弊候选：在 EVOLVE-BLOCK 里 import ref_solver（应被 preflight 拒绝）。"""
    p = d / "cheat.py"
    p.write_text(
        '#!/usr/bin/env python3\n'
        'from __future__ import annotations\n'
        'import json, sys\n'
        'def solve(inst):\n'
        '    # EVOLVE-BLOCK-START\n'
        '    from ref_solver import solve as ref\n'
        '    return ref(inst)["cuts"]\n'
        '    # EVOLVE-BLOCK-END\n'
        'def main():\n'
        '    inst=json.load(open(sys.argv[1]))\n'
        '    print(json.dumps({"cuts": solve(inst)}))\n'
        'if __name__ == "__main__": main()\n',
        encoding="utf-8",
    )
    return p


class TestSandboxEvaluator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(TASK / "verification"))
        cls.ev = _load_evaluator()

    def test_baseline_scores_and_valid(self):
        import os
        os.environ.pop("CUTTING_EVAL_GENERATE_SEED", None)
        r = self.ev.evaluate(str(TASK / "baseline" / "solver.py"))
        if isinstance(r, dict) and "metrics" in r:
            r = r["metrics"]
        self.assertEqual(r.get("valid"), 1.0)
        self.assertGreater(r.get("combined_score", 0.0), 0.0)

    def test_runtime_generation_adds_instances(self):
        import os
        os.environ["CUTTING_EVAL_GENERATE_SEED"] = "7"
        os.environ["CUTTING_EVAL_GENERATE_COUNT"] = "3"
        try:
            r = self.ev.evaluate(str(TASK / "baseline" / "solver.py"),
                                 data_dir=str(TASK / "verification" / "data" / "instances"))
            if isinstance(r, dict) and "metrics" in r:
                r = r["metrics"]
        finally:
            os.environ.pop("CUTTING_EVAL_GENERATE_SEED", None)
            os.environ.pop("CUTTING_EVAL_GENERATE_COUNT", None)
        gen = [k for k in r["per_instance"] if k.startswith("gen_")]
        self.assertEqual(len(gen), 3)

    def test_cheating_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            cheat = _write_cheat(Path(td))
            r = self.ev.evaluate(str(cheat),
                                 data_dir=str(TASK / "verification" / "data" / "instances"))
            if isinstance(r, dict) and "metrics" in r:
                r = r["metrics"]
            self.assertEqual(r.get("valid"), 0.0)

    def test_consistent_with_verification_evaluator(self):
        """沙箱入口与 verification/evaluate.py 应给出同样的 combined_score（数值一致）。"""
        import os
        os.environ.pop("CUTTING_EVAL_GENERATE_SEED", None)
        sandbox = self.ev.evaluate(str(TASK / "baseline" / "solver.py"),
                                   data_dir=str(TASK / "verification" / "data" / "instances"))
        if isinstance(sandbox, dict) and "metrics" in sandbox:
            sandbox = sandbox["metrics"]

        from evaluate import evaluate as ver_evaluate
        ver = ver_evaluate(str(TASK / "baseline" / "solver.py"),
                           data_dir=str(TASK / "verification" / "data" / "instances"))
        self.assertAlmostEqual(sandbox["combined_score"], ver["combined_score"], places=2)


if __name__ == "__main__":
    unittest.main()
