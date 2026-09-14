#!/usr/bin/env python3
"""Execute an Optics ``fiber_*`` candidate in its staged workspace.

``scenario.json`` supplies keyword arguments for the entrypoint in
``candidate_solver.py``. The result is written to ``submission.json`` as
``{"solution": ...}``. The scorer validates every field and computes the score;
the runner shares a process with candidate code and its output is untrusted.

The workspace does not include the verification directory. Filesystem access
beyond that workspace depends on the sandbox mode selected by the caller.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ARRAY_TAG = "__ndarray__"


def _rehydrate(obj):
    """Turn the tagged JSON scenario back into numpy arrays / plain values."""
    if isinstance(obj, dict):
        if ARRAY_TAG in obj:
            import numpy as np

            return np.asarray(obj[ARRAY_TAG], dtype=obj.get("dtype") or None)
        return {k: _rehydrate(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rehydrate(v) for v in obj]
    return obj


def _jsonable(obj):
    """Best-effort conversion of a solver result into JSON-safe values.

    Non-finite floats are preserved (``allow_nan``) rather than rejected here;
    the scorer owns the finiteness check so it can report a precise reason.
    """
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, bool, int, float)) or obj is None:
        return obj
    try:
        import numpy as np
    except Exception:  # pragma: no cover - numpy is always present in practice
        np = None
    if np is not None:
        if isinstance(obj, np.ndarray):
            return _jsonable(obj.tolist())
        if isinstance(obj, np.generic):
            return _jsonable(obj.item())
    if hasattr(obj, "tolist"):
        return _jsonable(obj.tolist())
    if hasattr(obj, "item"):
        return _jsonable(obj.item())
    return str(obj)


def _load_candidate(path: Path):
    spec = importlib.util.spec_from_file_location("candidate_solver", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load candidate module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate_solver"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--candidate", default="candidate_solver.py")
    parser.add_argument("--scenario", default="scenario.json")
    parser.add_argument("--output", default="submission.json")
    args = parser.parse_args()

    cwd = Path.cwd().resolve()
    payload = json.loads((cwd / args.scenario).read_text(encoding="utf-8"))
    kwargs = _rehydrate(payload.get("kwargs") or {})
    for name in payload.get("tuple_kwargs") or ():
        if name in kwargs and isinstance(kwargs[name], list):
            kwargs[name] = tuple(kwargs[name])

    module = _load_candidate(cwd / args.candidate)
    fn = getattr(module, args.entrypoint, None)
    if fn is None or not callable(fn):
        print(
            f"candidate does not define a callable '{args.entrypoint}'",
            file=sys.stderr,
        )
        return 3

    result = fn(**kwargs)
    if not isinstance(result, dict):
        print(f"entrypoint returned {type(result).__name__}, expected dict", file=sys.stderr)
        return 4

    (cwd / args.output).write_text(
        json.dumps({"solution": _jsonable(result)}, allow_nan=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
