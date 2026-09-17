from __future__ import annotations

from pathlib import Path
import tempfile
import textwrap
import unittest

from policy_runtime import PolicyCandidateError, PolicyProtocolError, PolicyRuntime, PolicyTimeoutError


ROOT = Path(__file__).resolve().parents[1]


class PolicyRuntimeTests(unittest.TestCase):
    def test_reasonable_candidate_round_trip(self) -> None:
        from simulator import EdgeServiceSimulator, SCENARIOS

        simulator = EdgeServiceSimulator(SCENARIOS[0])
        simulator._activate_pending_and_apply_failures()
        with PolicyRuntime(ROOT / "scripts" / "init.py") as policy:
            policy.reset_policy()
            action = policy.decide(simulator.observation())
        self.assertEqual(set(action), {"replicas", "routes"})

    def _candidate(self, source: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "candidate.py"
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return path

    def test_missing_decide_fails_closed(self) -> None:
        with self.assertRaises(PolicyCandidateError):
            PolicyRuntime(self._candidate("x = 1\n"))

    def test_infinite_loop_times_out(self) -> None:
        candidate = self._candidate(
            """
            def decide(observation):
                while True:
                    pass
            """
        )
        with PolicyRuntime(candidate, call_timeout_s=0.1, total_timeout_s=1.0) as policy:
            with self.assertRaises(PolicyTimeoutError):
                policy.decide({})

    def test_oversized_response_is_rejected(self) -> None:
        candidate = self._candidate(
            """
            def decide(observation):
                return {"replicas": [], "routes": [], "padding": "x" * 70000}
            """
        )
        with PolicyRuntime(candidate) as policy:
            with self.assertRaises((PolicyProtocolError, PolicyCandidateError)):
                policy.decide({})

    def test_non_json_result_is_rejected(self) -> None:
        candidate = self._candidate(
            """
            def decide(observation):
                return {"replicas": set(), "routes": []}
            """
        )
        with PolicyRuntime(candidate) as policy:
            with self.assertRaises(PolicyCandidateError):
                policy.decide({})

    def test_candidate_exception_is_reported(self) -> None:
        candidate = self._candidate(
            """
            def decide(observation):
                raise RuntimeError("intentional failure")
            """
        )
        with PolicyRuntime(candidate) as policy:
            with self.assertRaisesRegex(PolicyCandidateError, "intentional failure"):
                policy.decide({})

    def test_abrupt_process_exit_is_reported(self) -> None:
        candidate = self._candidate(
            """
            import os
            def decide(observation):
                os._exit(7)
            """
        )
        with PolicyRuntime(candidate) as policy:
            with self.assertRaises(PolicyCandidateError):
                policy.decide({})

    def test_non_json_stdout_cannot_corrupt_protocol(self) -> None:
        candidate = self._candidate(
            """
            def decide(observation):
                print("not-json protocol noise")
                return {"replicas": [], "routes": []}
            """
        )
        with PolicyRuntime(candidate) as policy:
            self.assertEqual(policy.decide({}), {"replicas": [], "routes": []})

    def test_stderr_spam_is_drained_and_tail_is_bounded(self) -> None:
        candidate = self._candidate(
            """
            import sys
            def decide(observation):
                sys.stderr.write("x" * 200000)
                sys.stderr.flush()
                return {"replicas": [], "routes": []}
            """
        )
        with PolicyRuntime(candidate) as policy:
            self.assertEqual(policy.decide({}), {"replicas": [], "routes": []})
            self.assertLessEqual(len(policy.stderr_tail.encode("utf-8")), 16 * 1024)

    def test_candidate_mutates_only_its_json_copy_of_observation(self) -> None:
        candidate = self._candidate(
            """
            def decide(observation):
                observation["nested"]["value"] = 99
                return {"seen": observation["nested"]["value"]}
            """
        )
        original = {"nested": {"value": 1}}
        with PolicyRuntime(candidate) as policy:
            self.assertEqual(policy.decide(original), {"seen": 99})
        self.assertEqual(original, {"nested": {"value": 1}})


if __name__ == "__main__":
    unittest.main()
