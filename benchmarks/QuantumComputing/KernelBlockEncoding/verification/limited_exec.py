"""Apply hard POSIX limits to this process, then exec a candidate program."""

from __future__ import annotations

import os
import resource
import sys


def _positive_integer(text: str, label: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise SystemExit(f"{label} must be an integer") from exc
    if value <= 0:
        raise SystemExit(f"{label} must be positive")
    return value


def main() -> int:
    if len(sys.argv) < 7 or sys.argv[5] != "--":
        raise SystemExit(
            "usage: limited_exec.py MEMORY_MB CPU_SECONDS FILE_BYTES CWD -- "
            "PROGRAM [ARG ...]"
        )
    memory_mb = _positive_integer(sys.argv[1], "MEMORY_MB")
    cpu_seconds = _positive_integer(sys.argv[2], "CPU_SECONDS")
    file_bytes = _positive_integer(sys.argv[3], "FILE_BYTES")
    working_directory = os.path.abspath(sys.argv[4])
    program = os.path.abspath(sys.argv[6])
    arguments = [program, *sys.argv[7:]]

    # Session creation happens here, in a freshly spawned interpreter, so the
    # multithreaded evaluator never needs a fork-time callback.
    os.setsid()
    os.chdir(working_directory)
    memory_bytes = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except (ValueError, OSError):
        pass

    os.execv(program, arguments)
    raise AssertionError("unreachable")  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
