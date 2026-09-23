"""Sandbox-evaluator end-to-end tests (frontier_eval/evaluator.py).

The unified runtime runs the eval from the sandbox: the sandbox evaluator
loads `verification/evaluate.py` (copied in), and the generation path
host-loads `generator.py` via FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR.
These tests lock that wiring so a refactor cannot silently break the sandbox
path (the review finding that flagged no end-to-end sandbox coverage).
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

TASK_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = TASK_ROOT / "frontier_eval" / "evaluator.py"
BASELINE = TASK_ROOT / "baseline" / "solver.py"

_spec = importlib.util.spec_from_file_location("_sandbox_eval", EVALUATOR)
_sb = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_sb)


class TestSandboxBaseline(unittest.TestCase):
    def test_baseline_scores(self):
        m = _sb.evaluate(str(BASELINE))["metrics"]
        self.assertEqual(m["valid"], 1.0)
        self.assertEqual(m["num_instances"], 8)
        self.assertGreater(m["combined_score"], 100.0)


class TestSandboxHostLoad(unittest.TestCase):
    def test_generation_host_loads_generator(self):
        # Sandbox view: the host benchmark dir is exposed via the env var.
        os.environ["FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR"] = str(TASK_ROOT)
        os.environ["TELECOM_EVAL_GENERATE_SEED"] = "7"
        os.environ["TELECOM_EVAL_GENERATE_COUNT"] = "4"
        try:
            m = _sb.evaluate(str(BASELINE))["metrics"]
        finally:
            os.environ.pop("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", None)
            os.environ.pop("TELECOM_EVAL_GENERATE_SEED", None)
            os.environ.pop("TELECOM_EVAL_GENERATE_COUNT", None)
        self.assertEqual(m["valid"], 1.0)
        self.assertGreaterEqual(m["num_instances"], 12)  # 8 fixed + generated


class TestSandboxOfficialMode(unittest.TestCase):
    """official mode: mandatory generation, public instances excluded."""

    def _clear(self):
        for key in (
            "TELECOM_EVAL_MODE",
            "TELECOM_EVAL_GENERATE_SEED",
            "TELECOM_EVAL_GENERATE_COUNT",
            "TELECOM_EVAL_TIME_BUDGET",
            "FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR",
        ):
            os.environ.pop(key, None)

    def test_official_mode_requires_seed(self):
        self._clear()
        os.environ["TELECOM_EVAL_MODE"] = "official"
        try:
            with self.assertRaises(RuntimeError) as ctx:
                _sb.evaluate(str(BASELINE))
        finally:
            self._clear()
        self.assertIn("TELECOM_EVAL_GENERATE_SEED", str(ctx.exception))

    def test_official_mode_excludes_public_instances(self):
        self._clear()
        os.environ["TELECOM_EVAL_MODE"] = "official"
        os.environ["TELECOM_EVAL_GENERATE_SEED"] = "5"
        os.environ["TELECOM_EVAL_GENERATE_COUNT"] = "4"
        os.environ["FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR"] = str(TASK_ROOT)
        try:
            m = _sb.evaluate(str(BASELINE))["metrics"]
        finally:
            self._clear()
        self.assertEqual(m["num_fixed_instances"], 0)
        self.assertEqual(m["num_generated_instances"], 4)
        self.assertEqual(m["valid"], 1.0)

    def test_time_budget_env_is_respected(self):
        self._clear()
        os.environ["TELECOM_EVAL_TIME_BUDGET"] = "10"
        try:
            m = _sb.evaluate(str(BASELINE))["metrics"]
        finally:
            self._clear()
        self.assertEqual(m["time_budget_s"], 10.0)


class TestEvalCommandSelectsOfficialMode(unittest.TestCase):
    """The framework reads eval_command.txt; it must select official mode.

    Without this, dropping the prefix would silently revert the framework path
    to local (public-instance) scoring -- the exact hole review blocker 1 closed.
    """

    def test_eval_command_file_selects_official_mode(self):
        cmd = (TASK_ROOT / "frontier_eval" / "eval_command.txt").read_text(encoding="utf-8")
        self.assertIn("TELECOM_EVAL_MODE=official", cmd)


class TestSandboxRejectsRefSolver(unittest.TestCase):
    def test_ref_solver_cheat_rejected(self):
        src = BASELINE.read_text(encoding="utf-8")
        start = src.find("# EVOLVE-BLOCK-START")
        end = src.find("# EVOLVE-BLOCK-END")
        injected = (
            src[: start + len("# EVOLVE-BLOCK-START")]
            + "\n    from verification.ref_solver import solve\n    return solve(inst)\n"
            + src[end:]
        )
        tmp = Path(tempfile.mkdtemp(prefix="tb_cheat_"))
        cand = tmp / "cheat.py"
        cand.write_text(injected, encoding="utf-8")
        try:
            m = _sb.evaluate(str(cand))["metrics"]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(m["valid"], 0.0)
        self.assertEqual(m["combined_score"], 0.0)
        # rejected by the static check (not merely by a runtime crash): the
        # reported reason must name the forbidden reference token
        reasons = [r for info in m["per_instance"].values()
                   for r in info.get("reasons", [])]
        self.assertTrue(any("ref_solver" in r for r in reasons),
                        f"expected a ref_solver preflight reason, got {reasons!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
