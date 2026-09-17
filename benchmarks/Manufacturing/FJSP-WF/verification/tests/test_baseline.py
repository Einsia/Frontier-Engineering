import json, os, subprocess, sys, unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
BENCHMARK_DIR = TEST_DIR.parents[1]
REPO_ROOT = BENCHMARK_DIR.parents[2]
VERIFICATION_DIR = BENCHMARK_DIR / "verification"
BASELINE_PATH = BENCHMARK_DIR / "baseline" / "solution.py"
SOLVER_PATH = BENCHMARK_DIR / "scripts" / "init.py"

class TestBaselineValidSchedules(unittest.TestCase):
    def _evaluate_candidate(self, candidate_path, max_instances=None):
        cmd = [sys.executable, str(VERIFICATION_DIR / "evaluator.py"), str(candidate_path)]
        if max_instances:
            cmd.extend(["--max-instances", str(max_instances)])
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
        return proc

    def test_baseline_on_official_first_two(self):
        proc = self._evaluate_candidate(SOLVER_PATH, max_instances=2)
        self.assertEqual(proc.returncode, 0, f"Evaluator failed: {proc.stderr}")
        lines = proc.stdout.splitlines()
        instance_lines = [l for l in lines if l.strip() and "|" in l and "ok" in l]
        self.assertGreaterEqual(len(instance_lines), 2)

    def test_baseline_fails_due_to_evolve_check(self):
        proc = self._evaluate_candidate(BASELINE_PATH, max_instances=1)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("EVOLVE-BLOCK", proc.stderr)

    def test_solver_on_synthetic(self):
        proc = self._evaluate_candidate(SOLVER_PATH, max_instances=3)
        self.assertEqual(proc.returncode, 0, f"Solver failed: {proc.stderr}")
        valid_count = proc.stdout.count("| ok")
        self.assertGreaterEqual(valid_count, 1)

if __name__ == "__main__":
    unittest.main()
