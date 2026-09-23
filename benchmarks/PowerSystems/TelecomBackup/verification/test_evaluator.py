"""Unit tests for verification/evaluate.py (stdlib unittest, no third-party deps).

Run from the TelecomBackup task directory:
    python verification/test_evaluator.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate as ev  # noqa: E402
from generator import generate  # noqa: E402

TASK_ROOT = Path(__file__).resolve().parents[1]
BASELINE = TASK_ROOT / "baseline" / "solver.py"

ALWAYS_ON = (
    "# EVOLVE-BLOCK-START\n"
    "def solve(inst):\n"
    "    k = len(inst['groups']); T = inst['horizon']\n"
    "    return [[[0, T]] for _ in range(k)]\n"
    "# EVOLVE-BLOCK-END\n"
    "import json, sys\n"
    "inst = json.load(open(sys.argv[1], encoding='utf-8'))\n"
    "print(json.dumps({'on': solve(inst)}))\n"
)


class EvaluatorTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="telecom_eval_test_"))
        self.inst_dir = self.tmp / "instances"
        self.inst_dir.mkdir()
        # 3 个固定实例（seed 派生），使评测稳定
        for i in range(3):
            inst = generate(1000 + i, 20 + 8 * i)
            (self.inst_dir / f"instance_{i}.json").write_text(
                json.dumps(inst), encoding="utf-8"
            )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        for key in (
            "TELECOM_EVAL_MODE",
            "TELECOM_EVAL_GENERATE_SEED",
            "TELECOM_EVAL_GENERATE_COUNT",
            "TELECOM_EVAL_REFERENCE",
            "TELECOM_EVAL_TIME_BUDGET",
            "FRONTIER_EVAL_EVALUATOR_TIMEOUT_S",
        ):
            os.environ.pop(key, None)

    def _write(self, name: str, src: str) -> Path:
        p = self.tmp / name
        p.write_text(src, encoding="utf-8")
        return p

    def _run(self, solver: Path) -> dict:
        return ev.evaluate(str(solver), time_budget=30.0, data_dir=self.inst_dir)

    def test_always_on_scores_positive_and_valid(self):
        solver = self._write("always_on.py", ALWAYS_ON)
        result = self._run(solver)
        self.assertEqual(result["valid"], 1.0)
        self.assertGreater(result["combined_score"], 0.0)
        self.assertEqual(result["num_instances"], 3)

    def test_malformed_output_scores_zero(self):
        solver = self._write("bad.py", "print('not json')\n")
        result = self._run(solver)
        self.assertEqual(result["combined_score"], 0.0)
        self.assertEqual(result["valid"], 0.0)

    def test_timeout_scores_zero(self):
        solver = self._write("slow.py", "import time; time.sleep(60)\n")
        result = ev.evaluate(str(solver), time_budget=0.5, data_dir=self.inst_dir)
        self.assertEqual(result["combined_score"], 0.0)
        self.assertEqual(result["valid"], 0.0)

    def test_hardcoded_candidate_fails_preflight(self):
        src = ALWAYS_ON.replace(
            "    return [[[0, T]] for _ in range(k)]",
            "    table = {'instance_0': [[[0, 48]]]}\n"
            "    return table.get('instance_0', [[[0, T]] for _ in range(k)])",
            1,
        )
        solver = self._write("hardcode.py", src)
        result = self._run(solver)
        self.assertEqual(result["valid"], 0.0)
        self.assertTrue(
            any("preflight" in v.get("status", "") for v in result["per_instance"].values())
        )

    def test_missing_program_returns_error(self):
        result = self._run(self.tmp / "nope.py")
        self.assertEqual(result["valid"], 0.0)
        self.assertIn("error", result)

    def test_generate_seed_adds_instances(self):
        os.environ["TELECOM_EVAL_GENERATE_SEED"] = "7"
        os.environ["TELECOM_EVAL_GENERATE_COUNT"] = "4"
        solver = self._write("always_on2.py", ALWAYS_ON)
        result = self._run(solver)
        self.assertEqual(result["num_instances"], 3 + 4)
        self.assertEqual(result["generate_seed"], 7)
        self.assertEqual(result["valid"], 1.0)

    def test_generated_instances_are_reproducible(self):
        os.environ["TELECOM_EVAL_GENERATE_SEED"] = "7"
        os.environ["TELECOM_EVAL_GENERATE_COUNT"] = "2"
        solver = self._write("always_on3.py", ALWAYS_ON)
        a = self._run(solver)
        b = self._run(solver)
        self.assertEqual(a["combined_score"], b["combined_score"])

    # --- official mode: mandatory runtime generation (review blocker 1) ---

    def test_official_mode_requires_seed(self):
        """official mode without a seed must fail loudly, not score public instances."""
        solver = self._write("always_on4.py", ALWAYS_ON)
        with self.assertRaises(ev.OfficialModeConfigError):
            ev.evaluate(str(solver), time_budget=10.0, mode="official",
                        data_dir=self.inst_dir)

    def test_official_mode_scores_only_generated_instances(self):
        os.environ["TELECOM_EVAL_GENERATE_SEED"] = "42"
        os.environ["TELECOM_EVAL_GENERATE_COUNT"] = "3"
        solver = self._write("always_on5.py", ALWAYS_ON)
        result = ev.evaluate(str(solver), time_budget=10.0, mode="official",
                             data_dir=self.inst_dir)
        self.assertTrue(result["official"])
        self.assertEqual(result["num_fixed_instances"], 0)   # public instances excluded
        self.assertEqual(result["num_generated_instances"], 3)
        self.assertEqual(result["num_instances"], 3)
        self.assertEqual(result["generate_seed"], 42)
        self.assertEqual(result["valid"], 1.0)

    def test_bad_mode_value_rejected(self):
        solver = self._write("always_on6.py", ALWAYS_ON)
        os.environ["TELECOM_EVAL_MODE"] = "offical"  # typo
        with self.assertRaises(ev.OfficialModeConfigError):
            ev.evaluate(str(solver), time_budget=10.0)

    # --- reference scoring path (review blocker 2) ---

    def test_reference_bypasses_preflight(self):
        """--reference scores ref_solver.py, which normal preflight rejects."""
        ref = Path(ev.__file__).resolve().parent / "ref_solver.py"
        result = ev.evaluate(str(ref), time_budget=10.0, data_dir=self.inst_dir,
                             mode="local", reference=True)
        self.assertTrue(result["preflight_bypassed"])
        self.assertEqual(result["valid"], 1.0)
        self.assertGreater(result["combined_score"], 0.0)

    def test_reference_bypass_is_not_the_default(self):
        ref = Path(ev.__file__).resolve().parent / "ref_solver.py"
        result = ev.evaluate(str(ref), time_budget=10.0, data_dir=self.inst_dir,
                             mode="local")
        self.assertFalse(result["preflight_bypassed"])
        self.assertEqual(result["valid"], 0.0)

    # --- per-instance budget self-limits to the framework timeout (review item 3) ---

    def test_budget_self_limits_to_framework_timeout(self):
        os.environ["TELECOM_EVAL_GENERATE_SEED"] = "7"
        os.environ["TELECOM_EVAL_GENERATE_COUNT"] = "1"
        os.environ["FRONTIER_EVAL_EVALUATOR_TIMEOUT_S"] = "120"
        solver = self._write("always_on7.py", ALWAYS_ON)
        result = self._run(solver)
        self.assertTrue(result["budget_shrunk"])
        self.assertLess(result["effective_time_budget_s"], 60.0)
        self.assertEqual(result["framework_timeout_s"], 120.0)


if __name__ == "__main__":
    unittest.main()
