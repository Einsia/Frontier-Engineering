"""Run a candidate program in an isolated subprocess and hand back only data.

The unified harness (``frontier_eval/tasks/unified/evaluator/python.py``) makes
a single process boundary that contains *both* the per-task scoring script and
the candidate. For the score to be trustworthy, the candidate must live in a
separate process that returns only data -- never code, never a callable, never a
self-reported score.

This module is the shared version of the pattern already proven in
``benchmarks/StructuralOptimization/TopologyOptimization/verification/evaluator.py``
(the only benchmark that got it right) with the three-layer result validation
from ``benchmarks/Robotics/PIDTuning/frontier_eval/evaluator.py``.

It is deliberately pure-stdlib and sits outside any benchmark directory so that
a ``copy_files.txt`` of ``.`` never drags it into the sandbox where a candidate
could rewrite it.

Invariants that any caller must preserve (each is a hole found in a real audit):
1. Do all imports *before* calling run_candidate_isolated. Your scoring logic
   and every dependency must be resident in this process before the candidate
   ever runs. The candidate shares the filesystem with this process, so if you
   import the scorer from a path it can write to *after* it runs, you are
   loading code it just wrote.
2. The candidate delivers a *solution*, not a *score*. The score must be
   recomputed here from the returned data. Never trust a field the candidate
   reports (an eval once directly adopted ``submission["summary"]["score"]``).
3. A non-zero return code is always a failure. A surviving submission.json does
   not excuse a crash (one evaluator recorded the return code but kept scoring
   anyway).

What this does NOT give you
---------------------------
The child runs under the same uid as the scorer, so ``/proc/<ppid>/`` stays
readable: a candidate can recover the scorer's cwd via ``/proc/<ppid>/cwd`` and
read its command line and environment, and from there reach files this module
deliberately keeps out of the sandbox (a reference solution, an oracle). Passing
``env_allowlist`` and keeping the sandbox clean raise the cost of that but do not
close it -- there is no point pretending otherwise, and a partial mitigation here
would mostly buy the appearance of safety.

Closing it requires a real boundary the process model cannot provide: run the
task under ``task.runtime.isolation_mode=docker`` (the harness already implements
it, with ``--network none`` and a read-only rootfs), or a uid/mount namespace.
What this module *does* guarantee is the property the scores depend on: the
candidate cannot execute inside the scoring process, so it cannot rewrite the
scoring functions or the number they produce.
"""

from __future__ import annotations

import json
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "IsolatedRun",
    "run_candidate_isolated",
    "InvalidSubmissionError",
    "INVALID_COMBINED_SCORE",
]

# Matches the harness-wide sentinel for "the run is worthless".
INVALID_COMBINED_SCORE = -1e18


class InvalidSubmissionError(ValueError):
    """The candidate exited cleanly but its output is unusable."""


@dataclass
class IsolatedRun:
    """Everything the caller may legitimately consume about a candidate run."""

    returncode: int
    timed_out: bool
    stdout_tail: str
    stderr_tail: str
    outputs: dict[str, Path]
    workdir: Path
    runtime_s: float
    _output_bytes: dict[str, bytes] | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def read_output_bytes(self, rel: str) -> bytes:
        """Read a produced output's contents.

        The sandbox directory is removed when ``run_candidate_isolated``
        returns, so ``outputs`` still names the paths but no longer points at
        live files. Use this (or ``load_json_output``) to consume a result.
        """
        return self._output_bytes[rel]


def _read_bytes_or_copy(path: Path) -> bytes:
    if not path.exists():
        raise ValueError(f"input does not exist: {path}")
    return path.read_bytes() if path.is_file() else path


def _tail_text(path: Path, limit: int = 8000) -> str:
    """Last `limit` characters of a log file, decoded leniently."""
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > limit:
                f.seek(size - limit)
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _set_rlimits(rlimits: dict[str, int]) -> None:
    """Apply resource limits; best effort to avoid breaking the platform."""
    name_map = {
        "AS": resource.RLIMIT_AS,
        "CPU": resource.RLIMIT_CPU,
        "NOFILE": resource.RLIMIT_NOFILE,
        "FSIZE": resource.RLIMIT_FSIZE,
    }
    for name, value in rlimits.items():
        rname = name_map.get(name.upper())
        if rname is None:
            continue
        try:
            resource.setrlimit(rname, (value, value))
        except (OSError, ValueError):
            continue


def run_candidate_isolated(
    candidate_path: Path,
    *,
    inputs: dict[str, bytes | Path] | None = None,
    expected_outputs: Sequence[str] = (),
    timeout_s: float,
    argv: Sequence[str] = (),
    copy_into_workdir: bool = True,
    env_allowlist: Sequence[str] = (),
    rlimits: dict[str, int] | None = None,
    python: str = sys.executable,
) -> IsolatedRun:
    """Run ``candidate_path`` in a fresh temporary directory.

    Parameters
    ----------
    candidate_path:
        The candidate source file.
    inputs:
        Mapping of relative path -> bytes or a path to copy in, staged under the
        run's cwd as read-only inputs the candidate needs (a config, a problem
        definition). Copy the input into the sandbox rather than sharing a
        mutable file so the candidate cannot rewrite what the scorer later reads.
    expected_outputs:
        Relative paths (under the workdir) that must exist when the candidate
        finishes (e.g. ``("submission.json",)``). Each missing output is a
        failure even if the process exited 0.
    timeout_s:
        Hard wall-clock limit for the candidate. Required -- no default -- so a
        runaway candidate cannot hang the whole evaluation.
    argv:
        Extra CLI args appended after the candidate path (for a
        ``--prepared-input`` / ``--solution-output`` style contract).
    copy_into_workdir:
        ``True`` to copy the candidate into the sandbox and run from there
        (keeps ``sys.path[0]`` inside the sandbox, so the candidate cannot import
        the task's own helper modules); ``False`` to run in place (lets the
        candidate import task-provided helpers, but it can see the whole task
        tree). Match the surrounding benchmark's existing contract.
    env_allowlist:
        Environment variables to keep from the parent. Default ``()`` means
        inherit everything, matching existing behaviour; pass an explicit list
        to narrow what a candidate can see.
    rlimits:
        ``{"AS": int, "CPU": int, ...}`` resource limits applied in the child via
        a ``preexec_fn``. Applied best-effort; no limit is applied for missing
        keys.
    python:
        Interpreter to run the candidate with.

    Returns
    -------
    IsolatedRun
        All fields are observations, never authority. The caller must validate
        the outputs' *contents* (bounds, shape, sanity) and must recompute the
        score itself from those contents.
    """
    candidate_path = Path(candidate_path)
    workdir = Path(tempfile.mkdtemp(prefix="fe_candidate_")).resolve()
    start = time.time()
    # The workdir is removed in `finally`, so load produced outputs into memory
    # first and hand back the bytes, not paths that will dangle. Callers can
    # write them out themselves if they need a durable file.
    output_bytes: dict[str, bytes] = {}
    returncode_out = 0
    timed_out_out = False
    stdout_tail = ""
    stderr_tail = ""
    try:
        if copy_into_workdir:
            sandbox_program = workdir / candidate_path.name
            shutil.copy2(candidate_path, sandbox_program)
            program_argv = [str(sandbox_program)]
        else:
            program_argv = [str(candidate_path.resolve())]

        for rel, content in (inputs or {}).items():
            dest = workdir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, Path):
                shutil.copy2(content, dest)
            elif isinstance(content, bytes):
                dest.write_bytes(content)
            else:
                raise TypeError(f"input '{rel}' must be bytes or Path, got {type(content)}")

        env = None
        if env_allowlist:
            env = {k: os.environ[k] for k in env_allowlist if k in os.environ}

        def _preexec() -> None:
            if rlimits:
                _set_rlimits(rlimits)
            os.setsid()

        # Popen with output redirected to files, not pipes, for two reasons
        # that both showed up in practice:
        #
        #  * subprocess.run()'s timeout kills only the direct child, and the
        #    candidate is a session leader (see _preexec), so anything it
        #    spawned kept running -- still able to write files after we
        #    believed we had stopped it. We kill the whole process group.
        #  * a grandchild inherits the stdout/stderr pipes, so communicate()
        #    blocks on EOF until *it* exits, not until the candidate does. A
        #    candidate that forks a daemon and returns immediately would hang
        #    the evaluator until its timeout. Files have no such coupling --
        #    and they also avoid the 64KB pipe-buffer deadlock a chatty
        #    candidate causes when nothing drains the pipe.
        log_dir = Path(tempfile.mkdtemp(prefix="fe_candidate_log_")).resolve()
        out_path = log_dir / "stdout.txt"
        err_path = log_dir / "stderr.txt"
        try:
            with out_path.open("wb") as f_out, err_path.open("wb") as f_err:
                proc = subprocess.Popen(  # noqa: S603
                    [python, *program_argv, *argv],
                    cwd=str(workdir),
                    stdout=f_out,
                    stderr=f_err,
                    env=env,
                    preexec_fn=_preexec,
                )
                try:
                    pgid = os.getpgid(proc.pid)
                except OSError:
                    pgid = None

                def _kill_group() -> None:
                    """Kill everything the candidate started, not just what it left."""
                    if pgid is None or pgid == os.getpgrp():
                        # Never signal our own group: that takes the scorer with it.
                        return
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass

                try:
                    proc.wait(timeout=timeout_s)
                    timed_out_out = False
                except subprocess.TimeoutExpired:
                    timed_out_out = True
                    _kill_group()
                    proc.kill()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        pass

            stdout_tail = _tail_text(out_path)
            stderr_tail = _tail_text(err_path)

            if timed_out_out:
                _kill_group()
                return IsolatedRun(
                    returncode=-1,
                    timed_out=True,
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                    outputs={},
                    workdir=workdir,
                    runtime_s=time.time() - start,
                    _output_bytes={},
                )
        finally:
            shutil.rmtree(log_dir, ignore_errors=True)

        # The candidate exited, but a process it forked may not have. Reap the
        # group before reading outputs, so nothing can still be writing to them.
        _kill_group()

        returncode_out = proc.returncode

        for rel in expected_outputs:
            path = workdir / rel
            if not path.is_file():
                raise InvalidSubmissionError(
                    f"expected output '{rel}' not produced (returncode={proc.returncode})"
                )
            output_bytes[rel] = path.read_bytes()

        out_paths = {rel: workdir / rel for rel in expected_outputs}
        run = IsolatedRun(
            returncode=returncode_out,
            timed_out=timed_out_out,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            outputs=out_paths,
            workdir=workdir,
            runtime_s=time.time() - start,
        )
        # Stash the bytes on the run so callers can read them after rmtree.
        setattr(run, "_output_bytes", output_bytes)
        return run
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def load_json_output(run: IsolatedRun, rel: str = "submission.json") -> dict[str, Any]:
    """Read a produced output as JSON and fail loudly if it is not valid."""
    try:
        data = json.loads(run.read_output_bytes(rel).decode("utf-8"))
    except Exception as exc:
        raise InvalidSubmissionError(f"failed to parse {rel}: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidSubmissionError(f"{rel} must contain a JSON object")
    return data
