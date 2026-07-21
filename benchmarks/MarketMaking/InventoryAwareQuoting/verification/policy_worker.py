"""JSON-lines worker that hosts an untrusted market-making policy.

The simulator deliberately does not run in this process.  The worker receives only
the public observation for a step and returns the candidate's action.  This is
process isolation, not an operating-system security sandbox.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


# Keep private copies before candidate code has a chance to mutate module attributes.
_json_loads = json.loads
_json_dumps = json.dumps


def _protocol_streams():
    """Preserve the protocol descriptors and silence candidate stdout.

    Redirecting at the descriptor level also catches ``os.write(1, ...)`` and
    output through ``sys.__stdout__``.  The duplicated descriptor remains the
    worker's private protocol channel.
    """

    protocol_in = os.fdopen(os.dup(0), "r", encoding="utf-8", newline="\n")
    protocol_out = os.fdopen(
        os.dup(1), "w", encoding="utf-8", newline="\n", buffering=1
    )
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
    finally:
        os.close(devnull)
    return protocol_in, protocol_out


def _load_candidate(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("market_making_candidate", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load candidate from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "decide_quotes", None)):
        raise AttributeError("candidate must define callable decide_quotes(observation)")
    return module


def _error_payload(request_id: Any, exc: BaseException) -> dict[str, Any]:
    try:
        message = str(exc)[:500]
    except Exception:
        message = "failed to format candidate exception"
    return {
        "id": request_id,
        "ok": False,
        "error": {"type": type(exc).__name__, "message": message},
    }


def _send(stream: Any, payload: dict[str, Any]) -> None:
    stream.write(_json_dumps(payload, ensure_ascii=True, allow_nan=False) + "\n")
    stream.flush()


def main() -> int:
    protocol_in, protocol_out = _protocol_streams()
    if len(sys.argv) != 2:
        _send(protocol_out, _error_payload(None, ValueError("expected candidate path")))
        return 2

    try:
        candidate = _load_candidate(Path(sys.argv[1]).resolve())
    except BaseException as exc:
        _send(protocol_out, _error_payload(None, exc))
        return 1

    _send(protocol_out, {"id": None, "ok": True, "ready": True})
    for line in protocol_in:
        request_id: Any = None
        try:
            request = _json_loads(line)
            if not isinstance(request, dict):
                raise TypeError("request must be a JSON object")
            request_id = request.get("id")
            operation = request.get("op")
            if operation == "reset":
                reset = getattr(candidate, "reset_policy", None)
                if reset is not None:
                    if not callable(reset):
                        raise TypeError("reset_policy must be callable when defined")
                    reset()
                response = {"id": request_id, "ok": True}
            elif operation == "decide":
                observation = request.get("observation")
                actions = candidate.decide_quotes(observation)
                response = {
                    "id": request_id,
                    "ok": True,
                    "actions": actions,
                }
            elif operation == "shutdown":
                _send(protocol_out, {"id": request_id, "ok": True})
                return 0
            else:
                raise ValueError(f"unknown operation: {operation!r}")
            _send(protocol_out, response)
        except BaseException as exc:
            try:
                _send(protocol_out, _error_payload(request_id, exc))
            except BaseException:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
