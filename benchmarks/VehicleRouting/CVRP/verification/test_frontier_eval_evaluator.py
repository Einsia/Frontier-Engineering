"""Unit tests for the sandbox evaluator (frontier_eval/evaluator.py).

The sandbox evaluator is a self-contained copy of the verification evaluator
(parsing / validation / scoring / integrity checks embedded, since no
`verification/` files are copied into the sandbox). These tests exercise it
directly so the two copies cannot silently drift apart.

Run from the CVRP task directory:
    python verification/test_frontier_eval_evaluator.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

CVRP_ROOT = Path(__file__).resolve().parents[1]
SANDBOX_EVALUATOR = CVRP_ROOT / "frontier_eval" / "evaluator.py"

_spec = importlib.util.spec_from_file_location("_sandbox_evaluator", SANDBOX_EVALUATOR)
_sandbox = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_sandbox)

BASELINE = CVRP_ROOT / "baseline" / "solver.py"


class TestSandboxBaseline(unittest.TestCase):
    def test_baseline_scores_and_no_leak(self):
        m = _sandbox.evaluate(str(BASELINE))["metrics"]
        self.assertEqual(m["valid"], 1.0)
        self.assertEqual(m["instances"], 24.0)
        self.assertTrue(all(n.startswith(("VRP-", "VHO-")) for n in m["per_instance"]))
        self.assertGreater(m["combined_score"], 40.0)
        self.assertLess(m["combined_score"], 100.0)

    def test_artifacts_do_not_leak_reference(self):
        result = _sandbox.evaluate(str(BASELINE))
        self.assertNotIn("reference", result["artifacts"])
        self.assertEqual(result["artifacts"]["reference_instance_count"], 24.0)


class TestSandboxHeldoutFromHost(unittest.TestCase):
    def test_heldout_read_from_host_source(self):
        host = Path(tempfile.mkdtemp(prefix="cvrp_sb_host_"))
        heldout_dir = host / "data" / "instances_heldout"
        heldout_dir.mkdir(parents=True)
        shutil.copy2(
            CVRP_ROOT / "data" / "instances_heldout" / "VHO-22-3.vrp",
            heldout_dir / "VHO-22-3.vrp",
        )
        os.environ["FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR"] = str(host)
        os.environ["CVRP_EVAL_INSTANCES"] = "VRP-19-2 VHO-22-3"
        try:
            m = _sandbox.evaluate(str(BASELINE))["metrics"]
        finally:
            os.environ.pop("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", None)
            os.environ.pop("CVRP_EVAL_INSTANCES", None)
            shutil.rmtree(host, ignore_errors=True)
        self.assertEqual(m["valid"], 1.0)
        self.assertEqual(m["instances"], 2.0)
        self.assertIn("VHO-22-3", m["per_instance"])


class TestSandboxGeneration(unittest.TestCase):
    def test_generate_mode(self):
        # The sandbox evaluator generates instances by loading the host
        # generator/reference solver, so it needs the host source dir.
        os.environ["FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR"] = str(CVRP_ROOT)
        os.environ["CVRP_EVAL_GENERATE_SEED"] = "42"
        os.environ["CVRP_EVAL_GENERATE_COUNT"] = "4"
        try:
            m = _sandbox.evaluate(str(BASELINE))["metrics"]
        finally:
            os.environ.pop("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", None)
            os.environ.pop("CVRP_EVAL_GENERATE_SEED", None)
            os.environ.pop("CVRP_EVAL_GENERATE_COUNT", None)
        self.assertEqual(m["valid"], 1.0)
        self.assertEqual(m["instances"], 28.0)
        self.assertTrue(any(n.startswith("GEN-42-") for n in m["per_instance"]))


class TestSandboxPreflight(unittest.TestCase):
    def test_cheating_candidate_rejected(self):
        cheat = CVRP_ROOT / "baseline" / "solver.py"
        src = cheat.read_text(encoding="utf-8")
        start = src.find("# EVOLVE-BLOCK-START")
        end = src.find("# EVOLVE-BLOCK-END")
        injected = (
            src[: start + len("# EVOLVE-BLOCK-START")]
            + "\n    import ref_solver  # forbidden\n    return [[c] for c in range(1, instance['n'] + 1)]\n"
            + src[end:]
        )
        tmp = Path(tempfile.mkdtemp(prefix="cvrp_sb_cheat_"))
        cand = tmp / "cheat.py"
        cand.write_text(injected, encoding="utf-8")
        try:
            m = _sandbox.evaluate(str(cand))["metrics"]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(m["valid"], 0.0)
        self.assertEqual(m["combined_score"], 0.0)


class TestSandboxConsistency(unittest.TestCase):
    def test_parse_instance_matches_verification_copy(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import evaluator as verif  # noqa: E402

        inst = CVRP_ROOT / "data" / "instances" / "VRP-19-2.vrp"
        a = verif.parse_instance(inst)
        b = _sandbox.parse_instance(inst)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
