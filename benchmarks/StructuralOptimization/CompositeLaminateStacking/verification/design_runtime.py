"""Bounded parent-side runtime for laminate candidate modules."""

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
from typing import Any


MAX_RESPONSE_BYTES = 64 * 1024
_EOF = object()


class DesignRuntimeError(RuntimeError):
    pass


class DesignTimeoutError(DesignRuntimeError):
    pass


class DesignProtocolError(DesignRuntimeError):
    pass


class DesignCandidateError(DesignRuntimeError):
    pass


def _clean_environment() -> dict[str, str]:
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


class DesignRuntime:
    def __init__(
        self,
        candidate_path: str | Path,
        *,
        startup_timeout_s: float = 3.0,
        call_timeout_s: float = 8.0,
        total_timeout_s: float = 12.0,
    ) -> None:
        if min(startup_timeout_s, call_timeout_s, total_timeout_s) <= 0:
            raise ValueError("design timeouts must be positive")
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
        self._tempdir = Path(tempfile.mkdtemp(prefix="laminate_design_"))
        self._process: subprocess.Popen[bytes] | None = None
        try:
            copied_candidate = self._tempdir / "candidate.py"
            shutil.copy2(source, copied_candidate)
            worker = Path(__file__).with_name("design_worker.py").resolve()
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
            threading.Thread(target=self._read_stdout, args=(self._process.stdout,), daemon=True).start()
            threading.Thread(target=self._drain_stderr, args=(self._process.stderr,), daemon=True).start()
            ready = self._receive(startup_timeout_s, "candidate import")
            if not isinstance(ready, dict) or not ready.get("ok") or not ready.get("ready"):
                self._raise_response_error(ready, "candidate import")
        except BaseException:
            self.close(force=True)
            raise

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
            raise DesignTimeoutError("candidate total runtime budget exceeded")
        try:
            item = self._responses.get(timeout=timeout)
        except queue.Empty as exc:
            self.close(force=True)
            raise DesignTimeoutError(f"{operation} timed out after {timeout:.3f}s") from exc
        if item is _EOF:
            code = None if self._process is None else self._process.poll()
            detail = self.stderr_tail[-1000:]
            raise DesignCandidateError(
                f"candidate worker exited unexpectedly (code={code})"
                + (f": {detail}" if detail else "")
            )
        if not isinstance(item, bytes) or len(item) > MAX_RESPONSE_BYTES or not item.endswith(b"\n"):
            self.close(force=True)
            raise DesignProtocolError("candidate response exceeds 64 KiB or lacks newline")
        try:
            response = json.loads(item.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.close(force=True)
            raise DesignProtocolError("candidate returned invalid UTF-8 JSON") from exc
        if not isinstance(response, dict):
            raise DesignProtocolError("candidate response must be a JSON object")
        return response

    @staticmethod
    def _raise_response_error(response: Any, operation: str) -> None:
        if isinstance(response, dict):
            error = response.get("error")
            if isinstance(error, dict):
                raise DesignCandidateError(
                    f"{operation} failed: {error.get('type', 'CandidateError')}: "
                    f"{error.get('message', '')}"
                )
        raise DesignProtocolError(f"malformed response during {operation}")

    def _rpc(self, operation: str, **payload: Any) -> dict[str, Any]:
        if self._closed or self._process is None or self._process.poll() is not None:
            raise DesignCandidateError("candidate worker is not running")
        request_id = self._next_id
        self._next_id += 1
        encoded = (
            json.dumps(
                {"id": request_id, "op": operation, **payload},
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        try:
            assert self._process.stdin is not None
            self._process.stdin.write(encoded)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise DesignCandidateError("candidate worker closed its input") from exc
        response = self._receive(self.call_timeout_s, operation)
        if response.get("id") != request_id:
            self.close(force=True)
            raise DesignProtocolError("candidate response id does not match request")
        if not response.get("ok"):
            self._raise_response_error(response, operation)
        return response

    def design_laminates(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        response = self._rpc("design", cases=cases)
        designs = response.get("designs")
        if not isinstance(designs, dict):
            raise DesignProtocolError("design_laminates must return a JSON object")
        return designs

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

    def __enter__(self) -> "DesignRuntime":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close(force=True)
        except Exception:
            pass
