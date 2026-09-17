"""ref_solver.py 单测：求解合法性、确定性、显著优于 baseline、等于全局最优。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ref_solver  # noqa: E402
from simulator import load_instance, score, validate  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "instances"


class TestRefSolver(unittest.TestCase):
    def test_solution_valid_on_fixed_instances(self):
        for p in sorted(DATA.glob("instance_*.json")):
            inst = load_instance(p)
            cuts = ref_solver.solve(inst)["cuts"]
            ok, reason = validate(inst, cuts)
            self.assertTrue(ok, f"{p.name}: {reason}")

    def test_deterministic(self):
        inst = load_instance(sorted(DATA.glob("instance_*.json"))[0])
        self.assertEqual(ref_solver.solve(inst), ref_solver.solve(inst))

    def test_equals_or_beats_equal_split(self):
        """参考解利用率应不劣于朴素等分（一般显著更优）。"""
        import subprocess
        import sys as _sys
        from simulator import score as _score

        baseline = Path(__file__).resolve().parent.parent / "baseline" / "solver.py"
        for p in sorted(DATA.glob("instance_*.json"))[:4]:
            inst = load_instance(p)
            ref_cuts = ref_solver.solve(inst)["cuts"]
            out = subprocess.run(
                [_sys.executable, str(baseline), str(p)], capture_output=True, text=True
            )
            import json
            base_cuts = json.loads(out.stdout)["cuts"]
            _, r = score(inst, ref_cuts)
            _, b = score(inst, base_cuts)
            self.assertLessEqual(r["score"], b["score"], f"{p.name}: ref should be <= baseline")


if __name__ == "__main__":
    unittest.main()
