from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class BoundedResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    output_truncated: bool


def run_bounded(
    command: list[str], input_text: str, *, timeout_s: float, max_output_bytes: int
) -> BoundedResult:
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    stdout = bytearray()
    stderr = bytearray()
    truncated = [False, False]
    readers = [
        threading.Thread(
            target=_drain,
            args=(process.stdout, stdout, max_output_bytes, truncated, 0),
            daemon=True,
        ),
        threading.Thread(
            target=_drain,
            args=(process.stderr, stderr, max_output_bytes, truncated, 1),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()
    writer = threading.Thread(target=_write, args=(process, input_text.encode("utf-8")), daemon=True)
    writer.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            process.kill()
        process.wait()
    for reader in readers:
        reader.join()
    return BoundedResult(
        returncode=process.returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        timed_out=timed_out,
        output_truncated=any(truncated),
    )


def _drain(stream, target: bytearray, limit: int, truncated: list[bool], index: int) -> None:
    if stream is None:
        return
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            return
        remaining = limit - len(target)
        if remaining > 0:
            target.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated[index] = True


def _write(process: subprocess.Popen[bytes], content: bytes) -> None:
    if process.stdin is None:
        return
    try:
        process.stdin.write(content)
        process.stdin.close()
    except (BrokenPipeError, OSError):
        pass
