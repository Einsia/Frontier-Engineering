"""Unit tests for verification/validator.py (stdlib unittest, no third-party deps).

Run from the CVRP task directory:
    python verification/test_validator.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validator as vd  # noqa: E402
import evaluator as ev  # noqa: E402  (for parse_instance in probe selection)

CVRP_ROOT = Path(__file__).resolve().parents[1]
BASELINE = CVRP_ROOT / "baseline" / "solver.py"
BASELINE_SRC = BASELINE.read_text(encoding="utf-8")
INSTANCE_PATHS = sorted((CVRP_ROOT / "data" / "instances").glob("*.vrp")) + sorted(
    (CVRP_ROOT / "data" / "instances_heldout").glob("*.vrp")
)


class TestStaticChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cvrp_val_"))

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
        src = BASELINE_SRC.replace(
            '"""CVRP candidate solver', '"""HACKED candidate solver', 1
        )
        issues = self._check(src)
        self.assertTrue(any("outside EVOLVE-BLOCK" in i for i in issues))

    def test_import_reference_solver(self):
        src = BASELINE_SRC.replace(
            "def solve(instance):",
            "import verification.ref_solver as rs\ndef solve(instance):",
            1,
        )
        issues = self._check(src)
        self.assertTrue(any("ref_solver" in i for i in issues))

    def test_read_reference_json(self):
        src = BASELINE_SRC.replace(
            "def solve(instance):",
            'def solve(instance):\n    _ = open("data/reference.json").read()',
            1,
        )
        issues = self._check(src)
        self.assertTrue(any("reference.json" in i for i in issues))

    def test_hardcode_dict_key(self):
        src = BASELINE_SRC.replace(
            "def solve(instance):",
            'def solve(instance):\n    return {"VRP-19-2": [[1]]}[instance["name"]]',
            1,
        )
        issues = self._check(src)
        self.assertTrue(any("hardcode" in i for i in issues))

    def test_hardcode_equality(self):
        src = BASELINE_SRC.replace(
            "def solve(instance):",
            'def solve(instance):\n    if instance["name"] == "VHO-22-3":\n'
            '        return [[1]]',
            1,
        )
        issues = self._check(src)
        self.assertTrue(any("hardcode" in i for i in issues))

    def test_absolute_path(self):
        src = BASELINE_SRC + '\n# C:\\\\Users\\\\x\\\\reference.json\n'
        issues = self._check(src)
        self.assertTrue(any("absolute" in i for i in issues))

    def test_static_check_direct(self):
        # static_check_source with no baseline skips the fixed-region diff.
        issues = vd.static_check_source(BASELINE_SRC, baseline_src=None)
        self.assertEqual(issues, [])

    def test_comment_verification_not_rejected(self):
        # "verification" as a bare word (e.g. in a comment) is NOT a violation;
        # only import/from/module-path usage is.
        src = BASELINE_SRC.replace(
            "def solve(instance):",
            "# verification pass for small instances\ndef solve(instance):",
            1,
        )
        issues = self._check(src)
        self.assertFalse(any("verification" in i for i in issues))

    def test_import_verification_rejected(self):
        src = BASELINE_SRC.replace(
            "def solve(instance):",
            "import verification\nfrom verification import evaluator\n"
            "def solve(instance):",
            1,
        )
        issues = self._check(src)
        self.assertTrue(any("verification" in i for i in issues))


class TestDeterminism(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cvrp_det_test_"))
        self.inst_path = CVRP_ROOT / "data" / "instances" / "VRP-19-2.vrp"
        import sys as _sys

        self.python = _sys.executable

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_deterministic_baseline_passes(self):
        ok, note = vd.check_determinism(
            self.python, BASELINE, self.inst_path, timeout=60
        )
        self.assertTrue(ok, note)

    def test_nondeterministic_candidate_fails(self):
        src = BASELINE_SRC.replace(
            "def solve(instance):",
            "def solve(instance):\n    import random\n"
            "    return [[random.randint(1, instance['n'])\n"
            "             for _ in range(instance['n'])]]",
            1,
        )
        path = self.tmp / "nondet.py"
        path.write_text(src, encoding="utf-8")
        ok, note = vd.check_determinism(self.python, path, self.inst_path, timeout=60)
        self.assertFalse(ok)
        self.assertIn("not deterministic", note)

    def test_size_varied_randomness_detected(self):
        # Deterministic on small instances, random on large ones: the probe
        # selection must include a large instance, so this is caught.
        src = BASELINE_SRC.replace(
            "def solve(instance):",
            "def solve(instance):\n    import random\n"
            "    if instance['n'] <= 30:\n"
            "        return [[c] for c in range(1, instance['n'] + 1)]\n"
            "    return [[random.randint(1, instance['n'])\n"
            "             for _ in range(instance['n'])]]",
            1,
        )
        path = self.tmp / "sizevar.py"
        path.write_text(src, encoding="utf-8")

        probes = vd.select_determinism_probes(INSTANCE_PATHS, ev.parse_instance)
        self.assertEqual(len(probes), 3)
        # The largest probe has n > 30, so the candidate is random there.
        ok, note = vd.check_determinism(self.python, path, probes[-1], timeout=60)
        self.assertFalse(ok)
        self.assertIn("not deterministic", note)

    def test_probe_selection_spans_sizes(self):
        probes = vd.select_determinism_probes(INSTANCE_PATHS, ev.parse_instance)
        ns = sorted(ev.parse_instance(p)["n"] for p in probes)
        self.assertEqual(len(ns), 3)
        # min < median < max over the full set (24 instances).
        all_ns = sorted(ev.parse_instance(p)["n"] for p in INSTANCE_PATHS)
        self.assertEqual(ns[0], all_ns[0])
        self.assertEqual(ns[-1], all_ns[-1])


class TestCandidateEnvStripsFrontier(unittest.TestCase):
    """candidate_env must strip FRONTIER_ENGINEERING_ROOT (repo-root side channel)."""

    def test_strips_frontier_engineering_root(self):
        import os

        import validator as v

        os.environ["FRONTIER_ENGINEERING_ROOT"] = "C:/fake/repo"
        os.environ["FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR"] = "C:/fake/bench"
        try:
            env = v.candidate_env()
        finally:
            os.environ.pop("FRONTIER_ENGINEERING_ROOT", None)
            os.environ.pop("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", None)
        self.assertNotIn("FRONTIER_ENGINEERING_ROOT", env)
        self.assertNotIn("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", env)


if __name__ == "__main__":
    unittest.main(verbosity=2)
