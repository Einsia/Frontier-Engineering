"""Functional tests for benchmarks/_shared/candidate_sandbox.py.

These exercise the helper through a real subprocess, not by mocking subprocess.
The sandbox is created and removed per case; nothing here touches the repo's
benchmark data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "_shared"))

import candidate_sandbox as cs  # noqa: E402


def _write_candidate(script: str, root: Path) -> Path:
    path = root / "candidate.py"
    path.write_text(script, encoding="utf-8")
    return path


class TestSuccessPath:
    def test_collects_output_and_exit_code(self, tmp_path: Path) -> None:
        cand = _write_candidate(
            "import json\nfrom pathlib import Path\n"
            "Path('submission.json').write_text(json.dumps({'a': 1}))\n",
            tmp_path,
        )
        run = cs.run_candidate_isolated(cand, expected_outputs=("submission.json",), timeout_s=30)
        assert run.ok
        assert run.returncode == 0
        assert run.outputs["submission.json"].is_file() is False  # workdir cleaned up
        assert cs.load_json_output(run)["a"] == 1

    def test_stdin_inputs_are_staged(self, tmp_path: Path) -> None:
        cand = _write_candidate(
            "from pathlib import Path\nprint(Path('config.json').read_text())\n", tmp_path
        )
        run = cs.run_candidate_isolated(
            cand,
            inputs={"config.json": b'{"k": 7}'},
            timeout_s=30,
        )
        assert run.ok
        assert '"k"' in run.stdout_tail

    def test_copies_inputs_preserving_content(self, tmp_path: Path) -> None:
        src = tmp_path / "config.json"
        src.write_text('{"v": 3}', encoding="utf-8")
        cand = _write_candidate(
            "from pathlib import Path\nprint(Path('config.json').read_text())\n", tmp_path
        )
        run = cs.run_candidate_isolated(
            cand, inputs={"config.json": src}, timeout_s=30
        )
        assert run.ok
        assert "v" in run.stdout_tail


class TestFailurePath:
    def test_missing_expected_output_is_invalid(self, tmp_path: Path) -> None:
        cand = _write_candidate("pass\n", tmp_path)  # writes nothing
        with pytest.raises(cs.InvalidSubmissionError):
            cs.run_candidate_isolated(cand, expected_outputs=("submission.json",), timeout_s=30)

    def test_nonzero_exit_still_returns_run(self, tmp_path: Path) -> None:
        cand = _write_candidate("import sys\nsys.exit(3)\n", tmp_path)
        run = cs.run_candidate_isolated(cand, expected_outputs=(), timeout_s=30)
        assert not run.ok
        assert run.returncode == 3

    def test_timeout_marks_run(self, tmp_path: Path) -> None:
        cand = _write_candidate("import time\ntime.sleep(30)\n", tmp_path)
        run = cs.run_candidate_isolated(cand, expected_outputs=(), timeout_s=1)
        assert run.timed_out
        assert not run.ok

    def test_invalid_json_is_rejected(self, tmp_path: Path) -> None:
        cand = _write_candidate(
            "from pathlib import Path\nPath('submission.json').write_text('not json')\n",
            tmp_path,
        )
        run = cs.run_candidate_isolated(cand, expected_outputs=("submission.json",), timeout_s=30)
        assert run.ok
        with pytest.raises(cs.InvalidSubmissionError):
            cs.load_json_output(run)


class TestContractOptions:
    def test_copy_into_workdir_isolates_sys_path(self, tmp_path: Path) -> None:
        cand = _write_candidate("import sys\nprint(sys.path[0])\n", tmp_path)
        run = cs.run_candidate_isolated(cand, timeout_s=30, copy_into_workdir=True)
        assert run.ok
        # sys.path[0] is the sandbox dir, not tmp_path/src
        assert "candidate.py" in run.stdout_tail or str(tmp_path) not in run.stdout_tail

    def test_env_allowlist_narrows_environment(self, tmp_path: Path) -> None:
        import os

        os.environ["CS_TEST_ONLY_VAR"] = "visible"
        cand = _write_candidate(
            "import os\nprint(os.environ.get('CS_TEST_ONLY_VAR', 'GONE'))\n"
            "print(os.environ.get('PATH', 'GONE'))\n",
            tmp_path,
        )
        run = cs.run_candidate_isolated(
            cand, timeout_s=30, env_allowlist=("CS_TEST_ONLY_VAR",)
        )
        assert run.ok
        assert "visible" in run.stdout_tail
        assert "GONE" in run.stdout_tail  # PATH was filtered out


class TestProcessGroupCleanup:
    """A candidate's children must not outlive the candidate.

    run_candidate_isolated used subprocess.run(timeout=...), which kills only
    the direct child. The candidate is a session leader, so anything it forked
    survived -- still sharing the filesystem, still able to write to the task
    tree, after the evaluator believed it had stopped.
    """

    def test_orphan_of_a_timed_out_candidate_is_killed(self, tmp_path) -> None:
        import os
        import time as _time

        beacon = tmp_path / "orphan_alive.txt"
        program = tmp_path / "forker.py"
        program.write_text(
            "import os, sys, time\n"
            "if os.fork() == 0:\n"
            "    # the grandchild: outlive the parent and keep writing\n"
            "    for i in range(600):\n"
            f"        open({str(beacon)!r}, 'w').write(str(i))\n"
            "        time.sleep(0.05)\n"
            "    sys.exit(0)\n"
            "time.sleep(600)\n",
            encoding="utf-8",
        )
        run = cs.run_candidate_isolated(program, timeout_s=2, copy_into_workdir=True)
        assert run.timed_out

        # Let anything that survived prove it by advancing the beacon.
        first = beacon.read_text(encoding="utf-8") if beacon.exists() else None
        _time.sleep(1.0)
        second = beacon.read_text(encoding="utf-8") if beacon.exists() else None
        assert first == second, (
            f"a grandchild of the candidate is still running and writing "
            f"({first!r} -> {second!r})"
        )

    def test_orphan_of_a_cleanly_exiting_candidate_is_killed(self, tmp_path) -> None:
        """Exiting 0 must not be a way to leave a process behind either."""
        import time as _time

        beacon = tmp_path / "daemon_alive.txt"
        program = tmp_path / "daemonizer.py"
        program.write_text(
            "import os, sys, time\n"
            "if os.fork() == 0:\n"
            "    for i in range(600):\n"
            f"        open({str(beacon)!r}, 'w').write(str(i))\n"
            "        time.sleep(0.05)\n"
            "    sys.exit(0)\n"
            "open('submission.json', 'w').write('{}')\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        run = cs.run_candidate_isolated(
            program, expected_outputs=("submission.json",), timeout_s=30,
            copy_into_workdir=True,
        )
        assert run.ok
        first = beacon.read_text(encoding="utf-8") if beacon.exists() else None
        _time.sleep(1.0)
        second = beacon.read_text(encoding="utf-8") if beacon.exists() else None
        assert first == second, (
            f"a daemon forked by the candidate outlived it ({first!r} -> {second!r})"
        )

    def test_a_chatty_candidate_does_not_deadlock(self, tmp_path) -> None:
        """Output goes to files, so nothing has to drain a pipe.

        With stdout on a PIPE that no one reads, a candidate writing past the
        64KB buffer blocks forever and the run dies on timeout instead of
        succeeding.
        """
        program = tmp_path / "chatty.py"
        program.write_text(
            "import json, sys\n"
            "sys.stdout.write('x' * 4_000_000)\n"
            "sys.stderr.write('y' * 4_000_000)\n"
            "open('submission.json', 'w').write(json.dumps({'ok': True}))\n",
            encoding="utf-8",
        )
        run = cs.run_candidate_isolated(
            program, expected_outputs=("submission.json",), timeout_s=60,
            copy_into_workdir=True,
        )
        assert run.ok, f"chatty candidate did not finish: timed_out={run.timed_out}"
        assert cs.load_json_output(run)["ok"] is True
        # Tails are bounded, not the whole 4MB.
        assert len(run.stdout_tail) <= 8000
        assert len(run.stderr_tail) <= 8000
