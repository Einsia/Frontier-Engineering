from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from verification.policy_runtime import PolicyRuntime, PolicyTimeoutError
except ModuleNotFoundError:
    from policy_runtime import PolicyRuntime, PolicyTimeoutError


class PolicyRuntimeTests(unittest.TestCase):
    def _candidate(self, source: str) -> Path:
        directory = tempfile.TemporaryDirectory(prefix="bsm1_runtime_test_")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "candidate.py"
        path.write_text(source, encoding="utf-8")
        return path

    def test_stdout_is_isolated_from_the_json_protocol(self) -> None:
        candidate = self._candidate(
            "print('during import')\n"
            "def reset_controller(scenario): print('during reset')\n"
            "def control(observation):\n"
            "    print('during control')\n"
            "    return {'ok': 1}\n"
        )
        with PolicyRuntime(candidate) as runtime:
            runtime.reset({"scenario_id": "dry"})
            self.assertEqual(runtime.control({"step": 0}), {"ok": 1})

    def test_candidate_module_supports_postponed_dataclass_annotations(self) -> None:
        candidate = self._candidate(
            "from __future__ import annotations\n"
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class State:\n"
            "    previous: State | None = None\n"
            "state = State()\n"
            "def reset_controller(scenario): state.previous = None\n"
            "def control(observation): return {'loaded': state.previous is None}\n"
        )
        with PolicyRuntime(candidate) as runtime:
            runtime.reset({"scenario_id": "dry"})
            self.assertEqual(runtime.control({"step": 0}), {"loaded": True})

    def test_slow_control_is_terminated(self) -> None:
        candidate = self._candidate(
            "import time\n"
            "def reset_controller(scenario): pass\n"
            "def control(observation): time.sleep(0.2); return {}\n"
        )
        with PolicyRuntime(candidate, call_timeout_s=0.03) as runtime:
            runtime.reset({})
            with self.assertRaises(PolicyTimeoutError):
                runtime.control({})


if __name__ == "__main__":
    unittest.main()
