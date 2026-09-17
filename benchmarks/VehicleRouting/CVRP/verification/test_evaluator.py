"""Unit tests for the CVRP evaluator (stdlib unittest, no third-party deps).

Run from the CVRP task directory:
    python verification/test_evaluator.py
or from the repo root:
    python -m unittest discover -s benchmarks/VehicleRouting/CVRP/verification -p 'test_*.py'
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluator as ev  # noqa: E402

CVRP_ROOT = Path(__file__).resolve().parents[1]


class TestParseInstance(unittest.TestCase):
    def test_parse_public_instance(self):
        inst = ev.parse_instance(CVRP_ROOT / "data/instances" / "VRP-19-2.vrp")
        self.assertEqual(inst["name"], "VRP-19-2")
        self.assertEqual(inst["n"], 19)  # depot id 1, customers 2..20
        self.assertEqual(inst["capacity"], 270)
        self.assertEqual(len(inst["demand"]), 20)
        self.assertEqual(inst["demand"][0], 0)
        self.assertEqual(len(inst["distance"]), 20)
        self.assertEqual(len(inst["distance"][0]), 20)
        self.assertEqual(inst["distance"][0][0], 0)

    def test_parse_heldout_instance(self):
        inst = ev.parse_instance(CVRP_ROOT / "data/instances_heldout" / "VHO-22-3.vrp")
        self.assertEqual(inst["name"], "VHO-22-3")
        self.assertEqual(inst["n"], 22)


class TestRouteDistance(unittest.TestCase):
    def test_known_distance(self):
        # 1D line: depot at 0, customers at 3 and 7 => depot->3->7->depot = 17
        dist = [
            [0, 3, 7],
            [3, 0, 4],
            [7, 4, 0],
        ]
        self.assertEqual(ev.route_distance([[1, 2]], dist), 3 + 4 + 7)
        self.assertEqual(ev.route_distance([], dist), 0)


class TestValidate(unittest.TestCase):
    def setUp(self):
        self.inst = ev.parse_instance(CVRP_ROOT / "data/instances" / "VRP-19-2.vrp")

    def test_valid_single_customer_routes(self):
        routes = [[c] for c in range(1, self.inst["n"] + 1)]
        ok, note, dist = ev.validate(routes, self.inst)
        self.assertTrue(ok, note)
        self.assertIsInstance(dist, int)
        self.assertGreater(dist, 0)

    def test_duplicate_customer(self):
        routes = [[1, 1]] + [[c] for c in range(2, self.inst["n"] + 1)]
        ok, note, _ = ev.validate(routes, self.inst)
        self.assertFalse(ok)
        self.assertIn("more than once", note)

    def test_capacity_violation(self):
        routes = [list(range(1, self.inst["n"] + 1))]
        ok, note, _ = ev.validate(routes, self.inst)
        self.assertFalse(ok)
        self.assertIn("capacity", note)

    def test_missing_customer(self):
        routes = [[1, 2]]
        ok, note, _ = ev.validate(routes, self.inst)
        self.assertFalse(ok)
        self.assertIn("not served", note)

    def test_out_of_range_customer(self):
        routes = [[self.inst["n"] + 5]] + [[c] for c in range(1, self.inst["n"] + 1)]
        ok, note, _ = ev.validate(routes, self.inst)
        self.assertFalse(ok)
        self.assertIn("out of range", note)

    def test_non_integer_customer(self):
        routes = [[1.5]] + [[c] for c in range(2, self.inst["n"] + 1)]
        ok, note, _ = ev.validate(routes, self.inst)
        self.assertFalse(ok)


class TestCheckCandidate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cvrp_test_"))
        self.valid_candidate = CVRP_ROOT / "baseline" / "solver.py"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, content: str) -> Path:
        path = self.tmp / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_baseline_is_admissible(self):
        self.assertEqual(ev.check_candidate(self.valid_candidate), [])

    def test_import_reference_solver_rejected(self):
        src = self.valid_candidate.read_text(encoding="utf-8")
        bad = src.replace(
            "def solve(instance):", "import verification.ref_solver as rs\ndef solve(instance):", 1
        )
        path = self._write("bad_import.py", bad)
        issues = ev.check_candidate(path)
        self.assertTrue(any("verification" in i or "ref_solver" in i for i in issues))

    def test_hardcoding_rejected(self):
        src = self.valid_candidate.read_text(encoding="utf-8")
        bad = src.replace(
            "def solve(instance):",
            'def solve(instance):\n    if instance["name"] == "VRP-19-2": return [[1]]',
            1,
        )
        path = self._write("bad_hardcode.py", bad)
        issues = ev.check_candidate(path)
        self.assertTrue(any("hardcode" in i for i in issues))

    def test_missing_markers_rejected(self):
        src = self.valid_candidate.read_text(encoding="utf-8")
        bad = src.replace(ev.EVOLVE_START, "").replace(ev.EVOLVE_END, "")
        path = self._write("bad_markers.py", bad)
        issues = ev.check_candidate(path)
        self.assertTrue(any("EVOLVE-BLOCK" in i for i in issues))

    def test_absolute_path_rejected(self):
        src = self.valid_candidate.read_text(encoding="utf-8")
        bad = src + "\n# C:\\\\Users\\\\x\\\\reference.json\n"
        path = self._write("bad_path.py", bad)
        issues = ev.check_candidate(path)
        self.assertTrue(any("absolute" in i for i in issues))


class TestLoadReference(unittest.TestCase):
    def test_reference_contains_all_instances(self):
        ref = ev.load_reference()
        self.assertEqual(len(ref), 24)  # 12 public + 12 held-out
        for name in (
            "VRP-19-2",
            "VRP-60-9",
            "VHO-22-3",
            "VHO-58-9",
        ):
            self.assertIn(name, ref)
            self.assertGreater(ref[name], 0)


class TestEvaluateBaseline(unittest.TestCase):
    def test_baseline_scores(self):
        import os

        os.environ["CVRP_EVAL_INSTANCES"] = "VRP-19-2 VHO-22-3"
        try:
            result = ev.evaluate(str(CVRP_ROOT / "baseline" / "solver.py"))
        finally:
            os.environ.pop("CVRP_EVAL_INSTANCES", None)
        metrics = result["metrics"]
        self.assertEqual(metrics["valid"], 1.0)
        self.assertEqual(metrics["instances"], 2.0)
        self.assertGreater(metrics["combined_score"], 40.0)
        self.assertLess(metrics["combined_score"], 100.0)
        # artifacts must not leak reference distances
        artifacts = result["artifacts"]
        self.assertNotIn("reference", artifacts)
        self.assertEqual(artifacts["reference_instance_count"], 24.0)


class TestGenerateMode(unittest.TestCase):
    """Runtime instance generation (anti-hardcoding)."""

    def _run(self, seed, count=None, instances=None):
        import os

        os.environ["CVRP_EVAL_GENERATE_SEED"] = str(seed)
        if count is not None:
            os.environ["CVRP_EVAL_GENERATE_COUNT"] = str(count)
        if instances:
            os.environ["CVRP_EVAL_INSTANCES"] = instances
        try:
            return ev.evaluate(str(CVRP_ROOT / "baseline" / "solver.py"))["metrics"]
        finally:
            os.environ.pop("CVRP_EVAL_GENERATE_SEED", None)
            os.environ.pop("CVRP_EVAL_GENERATE_COUNT", None)
            os.environ.pop("CVRP_EVAL_INSTANCES", None)

    def test_generates_extra_instances(self):
        # 2 fixed + 4 generated = 6 instances, all valid.
        m = self._run(seed=42, count=4, instances="VRP-19-2 VHO-22-3")
        self.assertEqual(m["valid"], 1.0)
        self.assertEqual(m["instances"], 6.0)
        names = set(m["per_instance"].keys())
        self.assertIn("VRP-19-2", names)
        self.assertIn("VHO-22-3", names)
        self.assertTrue(any(n.startswith("GEN-42-") for n in names))

    def test_same_seed_deterministic(self):
        a = self._run(seed=42, count=3)
        b = self._run(seed=42, count=3)
        self.assertEqual(a["combined_score"], b["combined_score"])
        self.assertEqual(
            sorted(a["per_instance"].keys()), sorted(b["per_instance"].keys())
        )

    def test_different_seed_different_instances(self):
        a = self._run(seed=42, count=3)
        b = self._run(seed=7, count=3)
        self.assertNotEqual(
            sorted(a["per_instance"].keys()), sorted(b["per_instance"].keys())
        )

    def test_unset_seed_preserves_old_behaviour(self):
        import os

        os.environ["CVRP_EVAL_INSTANCES"] = "VRP-19-2 VHO-22-3"
        try:
            m = ev.evaluate(str(CVRP_ROOT / "baseline" / "solver.py"))["metrics"]
        finally:
            os.environ.pop("CVRP_EVAL_INSTANCES", None)
        self.assertEqual(m["instances"], 2.0)
        self.assertFalse(any(n.startswith("GEN-") for n in m["per_instance"]))


class TestHeldoutFromHost(unittest.TestCase):
    """Held-out instances are read from the host source dir, not the sandbox copy."""

    def test_heldout_read_from_host_source(self):
        import os
        import shutil
        import tempfile

        host = Path(tempfile.mkdtemp(prefix="cvrp_host_"))
        heldout_dir = host / "data" / "instances_heldout"
        heldout_dir.mkdir(parents=True)
        src_vho = CVRP_ROOT / "data" / "instances_heldout" / "VHO-22-3.vrp"
        shutil.copy2(src_vho, heldout_dir / "VHO-22-3.vrp")
        os.environ["FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR"] = str(host)
        os.environ["CVRP_EVAL_INSTANCES"] = "VRP-19-2 VHO-22-3"
        try:
            m = ev.evaluate(str(CVRP_ROOT / "baseline" / "solver.py"))["metrics"]
        finally:
            os.environ.pop("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", None)
            os.environ.pop("CVRP_EVAL_INSTANCES", None)
            shutil.rmtree(host, ignore_errors=True)
        self.assertEqual(m["valid"], 1.0)
        self.assertEqual(m["instances"], 2.0)
        self.assertIn("VRP-19-2", m["per_instance"])
        self.assertIn("VHO-22-3", m["per_instance"])


class TestSplitEvolveBlocks(unittest.TestCase):
    def test_split(self):
        src = "a\n# EVOLVE-BLOCK-START\nb\n# EVOLVE-BLOCK-END\nc\n"
        before, between, after = ev._split_evolve_blocks(src)
        self.assertEqual(before, "a\n")
        self.assertIn("b", between)
        self.assertEqual(after, "\nc\n")

    def test_missing_end(self):
        self.assertIsNone(ev._split_evolve_blocks("a\n# EVOLVE-BLOCK-START\nb\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
