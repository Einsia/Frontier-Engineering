"""Unit tests for verification/validator.py (stdlib unittest, no third-party deps).

Run from the TelecomBackup task directory:
    python verification/test_validator.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validator as vd  # noqa: E402

TASK_ROOT = Path(__file__).resolve().parents[1]
BASELINE = TASK_ROOT / "baseline" / "solver.py"
BASELINE_SRC = BASELINE.read_text(encoding="utf-8")


class TestStaticChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="telecom_val_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _check(self, src: str) -> list[str]:
        path = self.tmp / "candidate.py"
        path.write_text(src, encoding="utf-8")
        return vd.check_candidate(path, baseline_path=BASELINE)

    def test_baseline_is_clean(self):
        self.assertEqual(vd.check_candidate(BASELINE, baseline_path=BASELINE), [])

    def test_missing_markers(self):
        src = BASELINE_SRC.replace(vd.EVOLVE_START, "").replace(vd.EVOLVE_END, "")
        issues = self._check(src)
        self.assertTrue(any("EVOLVE-BLOCK" in i for i in issues))

    def test_outside_block_changed(self):
        src = BASELINE_SRC.replace('"""区域备电 baseline', '"""HACKED baseline', 1)
        issues = self._check(src)
        self.assertTrue(any("outside EVOLVE-BLOCK" in i for i in issues))

    def test_hardcode_by_instance_name(self):
        src = BASELINE_SRC.replace(
            'return [[[0, horizon]] for _ in range(k)]',
            'table = {"instance_1": [[[0, 48]]]}\n    return table',
            1,
        )
        issues = self._check(src)
        self.assertTrue(any("hardcodes" in i for i in issues))

    def test_import_generator(self):
        src = BASELINE_SRC.replace(
            'return [[[0, horizon]] for _ in range(k)]',
            "from generator import generate\n    return []",
            1,
        )
        issues = self._check(src)
        self.assertTrue(any("forbidden" in i for i in issues))

    def test_import_verification_evaluate_dotted(self):
        src = BASELINE_SRC.replace(
            'return [[[0, horizon]] for _ in range(k)]',
            "import verification.evaluate\n    return []",
            1,
        )
        issues = self._check(src)
        self.assertTrue(any("forbidden" in i for i in issues))

    def test_import_ref_solver_rejected(self):
        # P0：候选不得白嫖参考求解器（ref_solver）。
        src = BASELINE_SRC.replace(
            'return [[[0, horizon]] for _ in range(k)]',
            "from verification.ref_solver import solve\n    return solve(inst)",
            1,
        )
        issues = self._check(src)
        self.assertTrue(any("forbidden" in i or "ref_solver" in i for i in issues))

    def test_absolute_path(self):
        src = BASELINE_SRC.replace(
            'return [[[0, horizon]] for _ in range(k)]',
            'p = "C:\\\\Users\\\\secret"\n    return []',
            1,
        )
        issues = self._check(src)
        self.assertTrue(any("absolute" in i for i in issues))

    def test_whitebox_simulator_import_is_allowed(self):
        # 候选被允许用白盒计分器做内部搜索（Task.md 承诺的能力）
        src = BASELINE_SRC.replace(
            'return [[[0, horizon]] for _ in range(k)]',
            "from simulator import simulate\n    return [[[0, horizon]] for _ in range(k)]",
            1,
        )
        self.assertEqual(self._check(src), [])


class TestCandidateEnv(unittest.TestCase):
    def test_strips_frontier_and_telecom_vars(self):
        import os

        old = dict(os.environ)
        os.environ["FRONTIER_ENGINEERING_ROOT"] = "C:\\repo"
        os.environ["FRONTIER_EVAL_UNIFIED_PYTHON"] = "C:\\python"
        os.environ["TELECOM_EVAL_GENERATE_SEED"] = "42"
        os.environ["KEEP_ME"] = "x"
        try:
            env = vd.candidate_env()
        finally:
            os.environ.clear()
            os.environ.update(old)
        self.assertNotIn("FRONTIER_ENGINEERING_ROOT", env)
        self.assertNotIn("FRONTIER_EVAL_UNIFIED_PYTHON", env)
        self.assertNotIn("TELECOM_EVAL_GENERATE_SEED", env)
        self.assertEqual(env.get("KEEP_ME"), "x")


class TestDeterminism(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="telecom_det_"))
        self.inst = self.tmp / "inst.json"
        self.inst.write_text(json.dumps({
            "grid": {"width": 200.0, "height": 200.0, "nx": 2, "ny": 2},
            "sites": [[50, 50], [150, 150]],
            "groups": [[0], [1]],
            "battery": [12.0, 8.0],
            "demand": [0.5] * 4,
            "pt_dbm": 20.0, "n_exp": 6.0, "threshold": -105.0,
            "coverage_ratio": 0.4, "delta_min": 5.0, "horizon": 10, "site_cap": 60.0,
        }), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, src: str) -> Path:
        p = self.tmp / name
        p.write_text(src, encoding="utf-8")
        return p

    def test_deterministic_candidate_passes(self):
        solver = self._write("det.py", (
            "import json, sys\n"
            "inst = json.load(open(sys.argv[1], encoding='utf-8'))\n"
            "k = len(inst['groups']); T = inst['horizon']\n"
            "print(json.dumps({'on': [[[0, T]] for _ in range(k)]}))\n"
        ))
        ok, note = vd.check_determinism(sys.executable, solver, self.inst, 30.0)
        self.assertTrue(ok, note)

    def test_random_candidate_fails(self):
        solver = self._write("rand.py", (
            "import json, random, sys\n"
            "inst = json.load(open(sys.argv[1], encoding='utf-8'))\n"
            "k = len(inst['groups']); T = inst['horizon']\n"
            "iv = [[0, random.randint(0, T)] for _ in range(1)]\n"
            "print(json.dumps({'on': [iv for _ in range(k)]}))\n"
        ))
        ok, note = vd.check_determinism(sys.executable, solver, self.inst, 30.0)
        self.assertFalse(ok)
        self.assertIn("not deterministic", note)


if __name__ == "__main__":
    unittest.main()
