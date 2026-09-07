"""JSON-lines worker for a candidate policy. This is isolation, not an OS sandbox."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any


_loads = json.loads
_dumps = json.dumps


def _streams() -> tuple[Any, Any]:
    protocol_in = os.fdopen(os.dup(0), "r", encoding="utf-8", newline="\n")
    protocol_out = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n", buffering=1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
    finally:
        os.close(devnull)
    return protocol_in, protocol_out


def _send(stream: Any, payload: dict[str, Any]) -> None:
    stream.write(_dumps(payload, ensure_ascii=True, allow_nan=False) + "\n")
    stream.flush()


def _error(request_id: Any, exc: BaseException) -> dict[str, Any]:
    try:
        message = str(exc)[:500]
    except Exception:
        message = "failed to format candidate exception"
    return {"id": request_id, "ok": False, "error": {"type": type(exc).__name__, "message": message}}


def _load(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("edge_candidate", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load candidate from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "decide", None)):
        raise AttributeError("candidate must define callable decide(observation)")
    return module


def main() -> int:
    protocol_in, protocol_out = _streams()
    if len(sys.argv) != 2:
        _send(protocol_out, _error(None, ValueError("expected candidate path")))
        return 2
    try:
        candidate = _load(Path(sys.argv[1]).resolve())
    except BaseException as exc:
        _send(protocol_out, _error(None, exc))
        return 1
    _send(protocol_out, {"id": None, "ok": True, "ready": True})
    for line in protocol_in:
        request_id: Any = None
        try:
            request = _loads(line)
            if not isinstance(request, dict):
                raise TypeError("request must be an object")
            request_id = request.get("id")
            operation = request.get("op")
            if operation == "reset":
                reset = getattr(candidate, "reset_policy", None)
                if reset is not None:
                    if not callable(reset):
                        raise TypeError("reset_policy must be callable")
                    reset()
                response = {"id": request_id, "ok": True}
            elif operation == "decide":
                response = {"id": request_id, "ok": True, "action": candidate.decide(request.get("observation"))}
            elif operation == "shutdown":
                _send(protocol_out, {"id": request_id, "ok": True})
                return 0
            else:
                raise ValueError(f"unknown operation {operation!r}")
            _send(protocol_out, response)
        except BaseException as exc:
            try:
                _send(protocol_out, _error(request_id, exc))
            except BaseException:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
