import json, subprocess, sys, unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
BENCHMARK_DIR = TEST_DIR.parents[1]
REPO_ROOT = BENCHMARK_DIR.parents[2]
VERIFICATION_DIR = BENCHMARK_DIR / "verification"
BASELINE_PATH = BENCHMARK_DIR / "baseline" / "solution.py"
SOLVER_PATH = BENCHMARK_DIR / "scripts" / "init.py"

class TestEvaluatorRejectsInvalid(unittest.TestCase):
    def _evaluate_with_file(self, candidate_path):
        cmd = [sys.executable, str(VERIFICATION_DIR / "evaluator.py"), str(candidate_path), "--max-instances", "1"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
        return proc

    def test_solver_passes(self):
        proc = self._evaluate_with_file(SOLVER_PATH)
        self.assertEqual(proc.returncode, 0, f"Solver should pass: {proc.stderr}")

    def test_solver_output_has_metrics_json(self):
        proc = self._evaluate_with_file(SOLVER_PATH)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Metrics written to", proc.stdout)

    def test_evaluator_rejects_nonexistent_candidate(self):
        cmd = [sys.executable, str(VERIFICATION_DIR / "evaluator.py"), "nonexistent.py", "--max-instances", "1"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT))
        self.assertNotEqual(proc.returncode, 0)

    def test_evaluator_reports_baseline_metrics(self):
        proc = self._evaluate_with_file(SOLVER_PATH)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Summary", proc.stdout)

if __name__ == "__main__":
    unittest.main()
