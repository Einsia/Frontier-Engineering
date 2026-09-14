"""Run a candidate program in a subprocess and return serialized data.

This helper separates candidate execution from the per-task scorer. It lives
outside benchmark directories so task-local ``copy_files.txt`` entries do not
copy it into candidate workspaces.

Caller requirements
-------------------
1. Import scoring code and its dependencies before executing candidate code.
   Compatibility mode shares host files, so later imports from writable paths
   can read files modified by a candidate.
2. Recompute scores from validated solution data in the scorer. Candidate
   score fields, callables and validation verdicts are not authoritative.
3. Reject crashes, timeouts and malformed output even if a result file exists.

Isolation modes
---------------
Each candidate has its own PID namespace, including detached descendants.
Passing ``readonly_paths`` also restricts filesystem visibility to the runtime,
staged workspace and explicit inputs, and disables networking. Without that
argument, compatibility mode shares host files and does not protect private
data. A container containing both scorer and candidate does not replace this
inner boundary. Linux user namespaces and bubblewrap are required.
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

# Runtime controls only; API keys and scorer configuration are not candidate inputs.
CANDIDATE_RUNTIME_ENV = (
    "PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH", "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
    "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "NVIDIA_VISIBLE_DEVICES",
    "ROCR_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "PYTHONDONTWRITEBYTECODE",
)


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


def namespace_command(command: Sequence[str], workdir: Path,
                      readonly_paths: Sequence[Path] | None = None,
                      writable_paths: Sequence[Path] = (),
                      gpu: bool = False) -> list[str]:
    """Use a PID namespace for lifecycle control and optionally restrict files.

    With readonly_paths, only the Python runtime, staged files and explicitly
    supplied inputs are visible, and networking is disabled. Missing bubblewrap
    fails closed; a shared outer container is not a candidate boundary.
    """
    executable = shutil.which(str(command[0]))
    if executable is None:
        raise InvalidSubmissionError(f"candidate interpreter not found: {command[0]}")
    command = [str(Path(executable).absolute()), *command[1:]]
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise InvalidSubmissionError("candidate isolation requires bubblewrap (bwrap)")
    args = [bwrap, "--unshare-user", "--unshare-pid", "--die-with-parent"]
    if readonly_paths is None:
        args += ["--bind", "/", "/"]
    else:
        args += ["--unshare-net", "--tmpfs", "/tmp"]
        runtime = {Path("/usr"), Path("/bin"), Path("/sbin"), Path("/lib"), Path("/lib64"),
                   Path(sys.prefix), Path(sys.base_prefix)}
        exe = Path(command[0]).resolve()
        runtime.add(exe.parent.parent)
        # A caller may select a different venv from the scorer's interpreter.
        invoked = Path(command[0]).absolute()
        if invoked.is_symlink():
            target = Path(os.readlink(invoked))
            if not target.is_absolute():
                target = invoked.parent / target
            runtime.add(target.parent.parent)
        if (invoked.parent.parent / "pyvenv.cfg").is_file():
            runtime.add(invoked.parent.parent)
        runtime.update(Path(p).absolute() for p in readonly_paths)
        runtime.update(Path(p) for p in ("/etc/ld.so.cache", "/etc/localtime", "/etc/alternatives"))
        for path in sorted(runtime, key=lambda p: (len(p.parts), str(p))):
            if path == Path("/"):
                raise InvalidSubmissionError("refusing to expose the host root to a restricted candidate")
            if path.exists():
                args += ["--ro-bind", str(path), str(path)]
        args += ["--bind", str(workdir), str(workdir)]
        for path in writable_paths:
            args += ["--bind", str(path), str(path)]
    args += ["--proc", "/proc"]
    args += ["--dev-bind", "/dev", "/dev"] if readonly_paths is None else ["--dev", "/dev"]
    if readonly_paths is not None:
        args += ["--tmpfs", "/dev/shm"]
    if gpu:
        args += ["--ro-bind", "/sys", "/sys"]
        devices = set(Path("/dev").glob("nvidia*"))
        devices.update(p for p in (Path("/dev/kfd"), Path("/dev/dri")) if p.exists())
        for path in sorted(devices):
            args += ["--dev-bind", str(path), str(path)]
        rocm = Path("/opt/rocm")
        if rocm.exists():
            for path in sorted({rocm, rocm.resolve()}):
                args += ["--ro-bind", str(path), str(path)]
    args += ["--chdir", str(workdir), "--", *command]
    return args


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
    readonly_paths: Sequence[Path] | None = None,
    gpu: bool = False,
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
    readonly_paths:
        Explicit readable inputs for a restricted filesystem and no network.
        None retains filesystem compatibility while isolating process lifetime.

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
        if env_allowlist or readonly_paths is not None:
            allowed = env_allowlist or CANDIDATE_RUNTIME_ENV
            env = {k: os.environ[k] for k in allowed if k in os.environ}
        if readonly_paths is not None:
            env["HOME"] = str(workdir)
            env["XDG_CACHE_HOME"] = str(workdir / ".cache")

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
                    namespace_command([python, *program_argv, *argv], workdir, readonly_paths, gpu=gpu),
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
                    f"expected output '{rel}' not produced (returncode={proc.returncode}): {stderr_tail[-2000:]}"
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


def run_inventory_candidate(candidate_path: Path, task: str, **kwargs) -> IsolatedRun:
    """Accept both the original solve() interface and submission.json programs."""
    runner = r'''import json, runpy, sys
from pathlib import Path
sys.argv = ['candidate.py']
scope = runpy.run_path('candidate.py', run_name='__main__')
if not Path('submission.json').is_file():
    solve = scope.get('solve')
    if not callable(solve):
        raise ValueError('candidate must define solve() or write submission.json')
    task = json.loads(Path('_task.json').read_text())
    if task == 'finite_horizon_dp':
        cfg = json.loads(Path('config.json').read_text())
        s, S = solve(cfg['demand_mean'], cfg['demand_sd'])
        value = {'reorder_points': s, 'order_up_to_levels': S}
    elif task == 'disruption_eoqd':
        cfg = json.loads(Path('config.json').read_text())
        _, q, _ = solve(cfg)
        value = {'order_quantity': q}
    elif task == 'general_meio':
        value = {'base_stock': solve()}
    elif task == 'tree_gsm_safety_stock':
        value = {'cst': solve()}
    elif task == 'joint_replenishment':
        value = solve()
    else:
        raise ValueError('unsupported Inventory task')
    def scalar(v):
        if hasattr(v, 'tolist'):
            return v.tolist()
        raise TypeError(type(v).__name__)
    Path('submission.json').write_text(json.dumps(value, default=scalar))
'''
    inputs = dict(kwargs.pop("inputs", {}) or {})
    inputs.update({"candidate.py": Path(candidate_path).read_bytes(),
                   "_task.json": json.dumps(task).encode()})
    with tempfile.TemporaryDirectory(prefix="fe_inventory_runner_") as tmp:
        wrapper = Path(tmp) / "runner.py"
        wrapper.write_text(runner)
        return run_candidate_isolated(wrapper, inputs=inputs, readonly_paths=(), **kwargs)


def run_optics_candidate(candidate_path: Path, mode: str, **kwargs) -> IsolatedRun:
    """Stage a data-only adapter for legacy Optics functions and current scripts."""
    inputs = dict(kwargs.pop("inputs", {}) or {})
    inputs["candidate.py"] = Path(candidate_path).read_bytes()
    wrapper = Path(__file__).with_name("optics_candidate_runner.py")
    return run_candidate_isolated(wrapper, inputs=inputs, argv=(mode,),
                                  readonly_paths=(), gpu=True, **kwargs)
