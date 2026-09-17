from __future__ import annotations

import ctypes
import errno
import importlib.util
import json
import signal
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pyseccomp as seccomp


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, allow_nan=False, separators=(",", ":")), flush=True)


def load_candidate(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("frontier_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import candidate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "solve", None)):
        raise TypeError("candidate must define solve(case)")
    return module


def install_restrictions() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), "failed to enable no_new_privs")

    denied = {
        "open", "openat", "openat2", "creat",
        "read", "readv", "pread64", "preadv", "preadv2",
        "sendfile", "splice", "tee", "vmsplice", "copy_file_range",
        "socket", "socketpair", "connect", "accept", "accept4", "bind", "listen",
        "clone", "clone3", "fork", "vfork", "execve", "execveat",
        "ptrace", "mount", "umount2", "pivot_root", "chroot",
        "setns", "unshare", "bpf", "keyctl", "add_key", "request_key",
    }
    policy = seccomp.SyscallFilter(defaction=seccomp.ALLOW)
    for syscall in sorted(denied):
        try:
            policy.add_rule(seccomp.ERRNO(errno.EPERM), syscall)
        except RuntimeError:
            pass
    for syscall in ("write", "writev", "pwrite64", "pwritev", "pwritev2"):
        try:
            policy.add_rule(seccomp.ERRNO(errno.EPERM), syscall, seccomp.Arg(0, seccomp.GT, 2))
        except RuntimeError:
            pass
    policy.load()

    blocked_events = (
        "open", "os.open", "os.remove", "os.rename", "os.rmdir", "os.mkdir",
        "os.system", "os.exec", "os.spawn", "subprocess.Popen", "socket.",
        "ctypes.dlopen", "ctypes.dlsym",
    )

    def audit(event: str, _args: tuple[Any, ...]) -> None:
        if event.startswith(blocked_events):
            raise PermissionError(f"candidate operation prohibited: {event}")

    sys.addaudithook(audit)


def timeout_handler(_signum, _frame) -> None:
    raise TimeoutError("candidate solve() exceeded 2 seconds")


def main() -> int:
    if len(sys.argv) != 2:
        emit({"status": "error", "error": "worker requires one candidate path"})
        return 2
    try:
        candidate = load_candidate(Path(sys.argv[1]).resolve())
    except BaseException as exc:
        emit({"status": "error", "error": f"candidate import failed: {type(exc).__name__}: {exc}"})
        return 1

    emit({"status": "ready"})
    try:
        line = sys.stdin.readline()
        if not line:
            raise ValueError("worker received no scenario payload")
        payload = json.loads(line)
        install_restrictions()
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, 2.0)
        output = candidate.solve(payload)
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        emit({"status": "ok", "output": output})
        return 0
    except BaseException as exc:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        emit({"status": "error", "error": f"candidate solve failed: {type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
