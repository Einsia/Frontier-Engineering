from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from verification.evaluator import evaluate


class CandidateIsolationTests(unittest.TestCase):
    def evaluate_source(self, source: str):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.py"
            candidate.write_text(textwrap.dedent(source), encoding="utf-8")
            return evaluate(candidate)

    def assert_invalid(self, source: str, expected_error: str) -> None:
        metrics, artifacts = self.evaluate_source(source)
        self.assertEqual(metrics["valid"], 0.0)
        self.assertEqual(metrics["combined_score"], 0.0)
        self.assertIn(expected_error, artifacts["failure_summary"])

    def test_missing_vg_is_rejected(self):
        self.assert_invalid(
            """
            def solve(case):
                return {"pg_mw": [g["baseline_pg_mw"] for g in case["generators"]]}
            """,
            "both pg_mw and vg_pu",
        )

    def test_file_read_is_rejected(self):
        self.assert_invalid(
            """
            def solve(case):
                open("/etc/hostname").read()
            """,
            "operation prohibited: open",
        )

    def test_preopened_file_read_is_rejected(self):
        self.assert_invalid(
            """
            handle = open("/etc/hostname")
            def solve(case):
                handle.read()
            """,
            "Operation not permitted",
        )

    def test_preopened_file_write_is_rejected(self):
        self.assert_invalid(
            """
            handle = open("candidate-output.txt", "w")
            def solve(case):
                handle.write("forbidden")
                handle.flush()
            """,
            "Operation not permitted",
        )

    def test_subprocess_is_rejected(self):
        self.assert_invalid(
            """
            import subprocess
            def solve(case):
                subprocess.run(["/bin/true"])
            """,
            "operation prohibited: subprocess.Popen",
        )

    def test_network_is_rejected(self):
        self.assert_invalid(
            """
            import socket
            def solve(case):
                socket.socket()
            """,
            "operation prohibited: socket.__new__",
        )

    def test_nondeterminism_is_rejected(self):
        self.assert_invalid(
            """
            import random
            def solve(case):
                generators = case["generators"]
                return {
                    "pg_mw": [g["baseline_pg_mw"] + random.random() * 1e-6 for g in generators],
                    "vg_pu": [g["baseline_vg_pu"] for g in generators],
                }
            """,
            "must be deterministic",
        )

    def test_import_timeout_writes_invalid_result(self):
        self.assert_invalid("while True: pass", "import exceeded 10 seconds")

    def test_solve_timeout_writes_invalid_result(self):
        self.assert_invalid(
            """
            def solve(case):
                while True:
                    pass
            """,
            "solve() exceeded 2 seconds",
        )


if __name__ == "__main__":
    unittest.main()
