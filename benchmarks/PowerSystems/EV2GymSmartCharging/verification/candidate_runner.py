"""Trusted child-process driver for the EV2GymSmartCharging candidate.

EV2Gym is a genuine multi-step simulation (roughly a hundred `env.step()` calls
per case) where the candidate is asked for one action vector per step. A
one-shot subprocess-per-call would be far too slow, so instead this file is
launched *once per case* as a long-lived subprocess and exchanges line-delimited
JSON with the trusted evaluator over a dedicated pipe pair (never over
stdin/stdout, which the candidate's own prints could pollute):

* the request fd (read, number in ``$EV2GYM_REQUEST_FD``): one JSON object per
  line describing the current step's observed state
  (``_build_candidate_case`` output).
* the response fd (write, number in ``$EV2GYM_RESPONSE_FD``): one JSON object
  per line -- exactly what ``solve()`` returned, serialised. No validation
  happens here.

The actual `EV2Gym` environment, its statistics, and the reward all live in the
parent process; this subprocess never touches them, so a malicious candidate
can influence nothing beyond the action vector it returns for its own step --
which the parent still clips and bounds-checks before applying it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

REQUEST_FD_ENV = "EV2GYM_REQUEST_FD"
RESPONSE_FD_ENV = "EV2GYM_RESPONSE_FD"


def _load_candidate(path: Path):
    spec = importlib.util.spec_from_file_location("ev2gym_candidate", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load candidate module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    except ImportError:
        pass
    return value


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: candidate_runner.py <candidate.py>", file=sys.stderr)
        return 2
    candidate_path = Path(sys.argv[1]).expanduser().resolve()

    candidate = _load_candidate(candidate_path)
    solve_fn = getattr(candidate, "solve", None)
    if not callable(solve_fn):
        raise AttributeError("candidate module must define solve(case, max_sim_calls=0, simulate_fn=None)")

    request_stream = os.fdopen(int(os.environ[REQUEST_FD_ENV]), "r", encoding="utf-8")
    response_stream = os.fdopen(int(os.environ[RESPONSE_FD_ENV]), "w", encoding="utf-8")

    for line in request_stream:
        line = line.strip()
        if not line:
            continue
        case = json.loads(line)
        response: dict[str, Any] = {}
        try:
            result = solve_fn(case, max_sim_calls=0, simulate_fn=None)
            response["result"] = _jsonable(result)
        except Exception as exc:  # noqa: BLE001 - reported as data to the parent
            response["error"] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc(file=sys.stderr)
        response_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
        response_stream.flush()
        if "error" in response:
            break

    response_stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
