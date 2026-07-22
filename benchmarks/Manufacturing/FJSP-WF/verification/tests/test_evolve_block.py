import subprocess, sys, unittest, shutil
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
BENCHMARK_DIR = TEST_DIR.parents[1]
REPO_ROOT = BENCHMARK_DIR.parents[2]
VERIFICATION_DIR = BENCHMARK_DIR / "verification"
SOLVER_PATH = BENCHMARK_DIR / "scripts" / "init.py"

EVOLVE_START = "# EVOLVE-BLOCK-START"
EVOLVE_END = "# EVOLVE-BLOCK-END"
TMP_SOLVER_DIR = TEST_DIR / "_tmp_solver"

def _run_evaluator(candidate_path, max_instances=1):
    cmd = [sys.executable, str(VERIFICATION_DIR / "evaluator.py"),
           str(candidate_path), "--max-instances", str(max_instances)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
    return proc

class TestEvolveBlockProtection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TMP_SOLVER_DIR.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if TMP_SOLVER_DIR.exists():
            shutil.rmtree(TMP_SOLVER_DIR)

    def _make_modified_solver(self, insert_text_before=None, insert_text_after=None):
        """Copy solver to tmp, modify, return path. Preserve LF line endings."""
        dest = TMP_SOLVER_DIR / "scheduler.py"
        shutil.copy2(str(SOLVER_PATH), str(dest))
        with open(dest, "r", encoding="utf-8", newline="") as f:
            lines = f.readlines()
        if insert_text_before:
            for i, line in enumerate(lines):
                if line.strip() == EVOLVE_START:
                    lines.insert(i, insert_text_before)
                    break
        if insert_text_after:
            for i, line in enumerate(lines):
                if line.strip() == EVOLVE_END:
                    lines.insert(i + 1, insert_text_after)
                    break
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.writelines(lines)
        return dest

    def test_solver_passes_evolve_check(self):
        proc = _run_evaluator(SOLVER_PATH)
        self.assertEqual(proc.returncode, 0, f"Solver should pass: {proc.stderr}")

    def test_modified_before_block_fails(self):
        tmp_file = self._make_modified_solver(insert_text_before="# modified before block\n")
        proc = _run_evaluator(tmp_file)
        self.assertNotEqual(proc.returncode, 0)
        out = proc.stderr + proc.stdout
        self.assertIn("EVOLVE-BLOCK", out)
        self.assertIn("before", out.lower())

    def test_modified_after_block_fails(self):
        tmp_file = self._make_modified_solver(insert_text_after="# modified after block\n")
        proc = _run_evaluator(tmp_file)
        self.assertNotEqual(proc.returncode, 0)
        out = proc.stderr + proc.stdout
        self.assertIn("EVOLVE-BLOCK", out)
        self.assertIn("after", out.lower())

if __name__ == "__main__":
    unittest.main()
