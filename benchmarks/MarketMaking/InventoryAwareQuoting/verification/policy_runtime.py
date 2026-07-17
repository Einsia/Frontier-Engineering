"""Cross-platform parent-side runtime for isolated candidate policies."""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Mapping


MAX_RESPONSE_BYTES = 64 * 1024
_EOF = object()


class PolicyRuntimeError(RuntimeError):
    """Base error raised by the candidate policy runtime."""


class PolicyTimeoutError(PolicyRuntimeError):
    """The candidate exceeded an import, reset, decision, or total timeout."""


class PolicyProtocolError(PolicyRuntimeError):
    """The candidate worker returned malformed protocol data."""


class PolicyCandidateError(PolicyRuntimeError):
    """Candidate code raised an exception or exited unexpectedly."""


def _clean_environment() -> dict[str, str]:
    # Do not expose the evaluator's model/API credentials to generated code.
    allowed = {
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "NUMBER_OF_PROCESSORS",
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "WINDIR",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class PolicyRuntime:
    """Run one candidate module behind a bounded JSON-lines RPC interface.

    A runtime is persistent, so a stateful policy can act for an entire scenario.
    Create a fresh runtime for each scenario to guarantee state separation.
    """

    def __init__(
        self,
        candidate_path: str | Path,
        *,
        startup_timeout_s: float = 3.0,
        call_timeout_s: float = 0.25,
        total_timeout_s: float = 20.0,
    ) -> None:
        if min(startup_timeout_s, call_timeout_s, total_timeout_s) <= 0:
            raise ValueError("policy timeouts must be positive")
        source = Path(candidate_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)

        self.call_timeout_s = float(call_timeout_s)
        self._deadline = time.monotonic() + float(total_timeout_s)
        self._next_id = 1
        self._closed = False
        self._responses: queue.Queue[Any] = queue.Queue()
        self._stderr_chunks: deque[bytes] = deque()
        self._stderr_size = 0
        self._tempdir = Path(tempfile.mkdtemp(prefix="market_policy_"))
        self._process: subprocess.Popen[bytes] | None = None
        try:
            copied_candidate = self._tempdir / "candidate.py"
            shutil.copy2(source, copied_candidate)
            worker = Path(__file__).with_name("policy_worker.py").resolve()

            popen_kwargs: dict[str, Any] = {
                "cwd": str(self._tempdir),
                "env": _clean_environment(),
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "bufsize": 0,
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True

            self._process = subprocess.Popen(
                [sys.executable, "-I", "-u", str(worker), str(copied_candidate)],
                **popen_kwargs,
            )
            assert self._process.stdout is not None
            assert self._process.stderr is not None
            threading.Thread(
                target=self._read_stdout,
                args=(self._process.stdout,),
                daemon=True,
                name="policy-stdout",
            ).start()
            threading.Thread(
                target=self._drain_stderr,
                args=(self._process.stderr,),
                daemon=True,
                name="policy-stderr",
            ).start()
            ready = self._receive(float(startup_timeout_s), "candidate import")
            if not isinstance(ready, dict) or not ready.get("ok") or not ready.get("ready"):
                self._raise_response_error(ready, "candidate import")
        except BaseException:
            self.close(force=True)
            raise

    @property
    def pid(self) -> int | None:
        return None if self._process is None else self._process.pid

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def stderr_tail(self) -> str:
        return b"".join(self._stderr_chunks).decode("utf-8", errors="replace")

    def _read_stdout(self, stream: Any) -> None:
        try:
            while True:
                line = stream.readline(MAX_RESPONSE_BYTES + 1)
                if not line:
                    break
                self._responses.put(line)
                if len(line) > MAX_RESPONSE_BYTES or not line.endswith(b"\n"):
                    break
        finally:
            self._responses.put(_EOF)

    def _drain_stderr(self, stream: Any) -> None:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            self._stderr_chunks.append(chunk)
            self._stderr_size += len(chunk)
            while self._stderr_size > 16 * 1024 and self._stderr_chunks:
                self._stderr_size -= len(self._stderr_chunks.popleft())

    def _remaining(self) -> float:
        return self._deadline - time.monotonic()

    def _receive(self, timeout_s: float, operation: str) -> dict[str, Any]:
        timeout = min(float(timeout_s), self._remaining())
        if timeout <= 0:
            self.close(force=True)
            raise PolicyTimeoutError("candidate total runtime budget exceeded")
        try:
            item = self._responses.get(timeout=timeout)
        except queue.Empty as exc:
            self.close(force=True)
            raise PolicyTimeoutError(f"{operation} timed out after {timeout:.3f}s") from exc
        if item is _EOF:
            code = None if self._process is None else self._process.poll()
            detail = self.stderr_tail[-1000:]
            raise PolicyCandidateError(
                f"candidate worker exited unexpectedly (code={code})"
                + (f": {detail}" if detail else "")
            )
        if not isinstance(item, bytes) or len(item) > MAX_RESPONSE_BYTES or not item.endswith(b"\n"):
            self.close(force=True)
            raise PolicyProtocolError("candidate response exceeds 64 KiB or lacks newline")
        try:
            response = json.loads(item.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.close(force=True)
            raise PolicyProtocolError("candidate returned invalid UTF-8 JSON") from exc
        if not isinstance(response, dict):
            raise PolicyProtocolError("candidate response must be a JSON object")
        return response

    @staticmethod
    def _raise_response_error(response: Any, operation: str) -> None:
        if isinstance(response, dict):
            error = response.get("error")
            if isinstance(error, dict):
                kind = str(error.get("type", "CandidateError"))
                message = str(error.get("message", ""))
                raise PolicyCandidateError(f"{operation} failed: {kind}: {message}")
        raise PolicyProtocolError(f"malformed response during {operation}")

    def _rpc(self, operation: str, **payload: Any) -> dict[str, Any]:
        if self._closed or self._process is None or self._process.poll() is not None:
            raise PolicyCandidateError("candidate worker is not running")
        request_id = self._next_id
        self._next_id += 1
        request = {"id": request_id, "op": operation, **payload}
        try:
            encoded = (
                json.dumps(request, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise PolicyProtocolError("request is not finite JSON data") from exc
        try:
            assert self._process.stdin is not None
            self._process.stdin.write(encoded)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise PolicyCandidateError("candidate worker closed its input") from exc
        response = self._receive(self.call_timeout_s, operation)
        if response.get("id") != request_id:
            self.close(force=True)
            raise PolicyProtocolError("candidate response id does not match request")
        if not response.get("ok"):
            self._raise_response_error(response, operation)
        return response

    def reset_policy(self) -> None:
        self._rpc("reset")

    def decide_quotes(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        response = self._rpc("decide", observation=observation)
        actions = response.get("actions")
        if not isinstance(actions, dict):
            raise PolicyProtocolError("decide_quotes must return a JSON object")
        return actions

    def close(self, *, force: bool = False) -> None:
        if self._closed:
            return
        process = self._process
        if process is not None and process.poll() is None and not force:
            try:
                self._rpc("shutdown")
                process.wait(timeout=0.25)
            except Exception:
                force = True
        if process is not None and process.poll() is None:
            self._kill_process_tree(process)
        self._closed = True
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass
        shutil.rmtree(self._tempdir, ignore_errors=True)

    @staticmethod
    def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2.0,
                    check=False,
                )
            except Exception:
                process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)

    def __enter__(self) -> "PolicyRuntime":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close(force=True)
        except Exception:
            pass
