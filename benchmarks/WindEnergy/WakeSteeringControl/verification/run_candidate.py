from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
from typing import Any


def _blocked_network(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("network access is disabled during candidate evaluation")


def _load_candidate(path: Path):
    spec = importlib.util.spec_from_file_location("wake_steering_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import candidate: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "expected candidate path"}))
        return 0

    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    socket.socket = _blocked_network  # type: ignore[assignment]
    socket.create_connection = _blocked_network  # type: ignore[assignment]

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    try:
        payload = json.loads(sys.stdin.read())
        candidate_path = Path(sys.argv[1]).expanduser().resolve()
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
            module = _load_candidate(candidate_path)
            policy = getattr(module, "yaw_policy")
            args = (
                payload["wind_directions_deg"],
                payload["wind_speeds_mps"],
                payload["turbulence_intensities"],
                payload["layout_x_m"],
                payload["layout_y_m"],
            )
            first = _jsonable(policy(*args))
            second = _jsonable(policy(*args))
        result = {
            "ok": True,
            "first": first,
            "second": second,
            "captured_stdout": stdout_capture.getvalue()[-2000:],
            "captured_stderr": stderr_capture.getvalue()[-2000:],
        }
    except Exception as exc:
        result = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "captured_stdout": stdout_capture.getvalue()[-2000:],
            "captured_stderr": stderr_capture.getvalue()[-2000:],
        }

    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
