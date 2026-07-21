from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import verification.policy_runtime as policy_runtime_module
    from verification.policy_runtime import (
        PolicyCandidateError,
        PolicyRuntime,
        PolicyTimeoutError,
    )
except ModuleNotFoundError:  # pytest invoked from the repository root
    import policy_runtime as policy_runtime_module
    from policy_runtime import PolicyCandidateError, PolicyRuntime, PolicyTimeoutError


class PolicyRuntimeTests(unittest.TestCase):
    def _candidate(self, source: str) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="policy_test_"))
        path = directory / "candidate.py"
        path.write_text(source, encoding="utf-8")
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        return path

    def test_persistent_state_reset_and_stdout_isolation(self) -> None:
        candidate = self._candidate(
            """
import os
counter = 0
def reset_policy():
    global counter
    counter = 0
def decide_quotes(observation):
    global counter
    counter += 1
    print('ordinary candidate noise')
    os.write(1, b'raw candidate noise\\n')
    return {'NVDA': {'bid_offset_bps': 10 + counter}}
"""
        )
        runtime = PolicyRuntime(candidate, call_timeout_s=1.0)
        self.addCleanup(runtime.close)
        runtime.reset_policy()
        self.assertEqual(runtime.decide_quotes({})["NVDA"]["bid_offset_bps"], 11)
        self.assertEqual(runtime.decide_quotes({})["NVDA"]["bid_offset_bps"], 12)
        runtime.reset_policy()
        self.assertEqual(runtime.decide_quotes({})["NVDA"]["bid_offset_bps"], 11)

    def test_candidate_cannot_see_secret_environment_variables(self) -> None:
        candidate = self._candidate(
            """
import os
def decide_quotes(observation):
    return {'secret_visible': 'FRONTIER_TEST_SECRET' in os.environ}
"""
        )
        old = os.environ.get("FRONTIER_TEST_SECRET")
        os.environ["FRONTIER_TEST_SECRET"] = "do-not-copy"
        try:
            with PolicyRuntime(candidate, call_timeout_s=1.0) as runtime:
                self.assertFalse(runtime.decide_quotes({})["secret_visible"])
        finally:
            if old is None:
                os.environ.pop("FRONTIER_TEST_SECRET", None)
            else:
                os.environ["FRONTIER_TEST_SECRET"] = old

    def test_import_timeout_terminates_worker(self) -> None:
        candidate = self._candidate("while True:\n    pass\n")
        started = time.monotonic()
        with self.assertRaises(PolicyTimeoutError):
            PolicyRuntime(candidate, startup_timeout_s=0.5, total_timeout_s=2.0)
        self.assertLess(time.monotonic() - started, 4.0)

    def test_decision_timeout_terminates_worker(self) -> None:
        candidate = self._candidate(
            "def decide_quotes(observation):\n    while True:\n        pass\n"
        )
        runtime = PolicyRuntime(candidate, call_timeout_s=0.2, total_timeout_s=2.0)
        pid = runtime.pid
        with self.assertRaises(PolicyTimeoutError):
            runtime.decide_quotes({})
        self.assertFalse(runtime.is_running, f"worker {pid} survived timeout")

    def test_candidate_exception_is_reported(self) -> None:
        candidate = self._candidate(
            "def decide_quotes(observation):\n    raise ValueError('bad quote')\n"
        )
        with PolicyRuntime(candidate, call_timeout_s=1.0) as runtime:
            with self.assertRaisesRegex(PolicyCandidateError, "ValueError: bad quote"):
                runtime.decide_quotes({})

    def test_close_reaps_worker(self) -> None:
        candidate = self._candidate("def decide_quotes(observation):\n    return {}\n")
        runtime = PolicyRuntime(candidate, call_timeout_s=1.0)
        self.assertTrue(runtime.is_running)
        runtime.close()
        self.assertFalse(runtime.is_running)

    def test_copy_failure_cleans_temporary_directory(self) -> None:
        candidate = self._candidate("def decide_quotes(observation): return {}\n")
        parent = Path(tempfile.mkdtemp(prefix="policy_cleanup_test_"))
        target = parent / "runtime"
        self.addCleanup(lambda: __import__("shutil").rmtree(parent, ignore_errors=True))
        with (
            patch.object(policy_runtime_module.tempfile, "mkdtemp", return_value=str(target)),
            patch.object(policy_runtime_module.shutil, "copy2", side_effect=OSError("copy failed")),
        ):
            with self.assertRaisesRegex(OSError, "copy failed"):
                PolicyRuntime(candidate)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
