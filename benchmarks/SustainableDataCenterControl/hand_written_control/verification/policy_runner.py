"""Trusted child-process driver for the SustainDC hand-written control candidate.

The candidate must never be imported into the process that owns the SustainDC
environments, the NoOp reference, and the scoring functions: this benchmark
scores a candidate *relative to a NoOp baseline computed in the same process*,
so a candidate that could reach `benchmark_core`'s namespace could simply make
the reference look terrible instead of making itself good.

So the candidate is loaded here, in a throw-away subprocess launched once per
episode, and answers one request per environment step over a dedicated pipe
pair (not stdin/stdout, which the candidate's own prints would pollute):

* request fd (read, number in ``$SUSTAINDC_REQUEST_FD``): one JSON object per
  line -- either ``{"op": "reset"}`` or
  ``{"op": "act", "observations": {agent: [floats]}}``.
* response fd (write, number in ``$SUSTAINDC_RESPONSE_FD``): one JSON object per
  line -- ``{"actions": {...}}`` or ``{"error": "..."}``.

Observations are rebuilt as float32 numpy arrays before ``decide_actions`` sees
them, so the candidate-facing interface is byte-identical to the in-process one.
Nothing is validated here; ``benchmark_core._coerce_actions`` in the parent owns
that, and the parent's environment produces every number that is ever scored.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np

REQUEST_FD_ENV = "SUSTAINDC_REQUEST_FD"
RESPONSE_FD_ENV = "SUSTAINDC_RESPONSE_FD"


def _load_candidate(path: Path):
    spec = importlib.util.spec_from_file_location("benchmark_solution", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load solution module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "decide_actions"):
        raise AttributeError(f"{path} must define a decide_actions(observations) function.")
    return module


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: policy_runner.py <solution.py>", file=sys.stderr)
        return 2
    solution_path = Path(sys.argv[1]).expanduser().resolve()

    request_stream = os.fdopen(int(os.environ[REQUEST_FD_ENV]), "r", encoding="utf-8")
    response_stream = os.fdopen(int(os.environ[RESPONSE_FD_ENV]), "w", encoding="utf-8")

    try:
        policy = _load_candidate(solution_path)
    except Exception as exc:  # noqa: BLE001 - reported as data to the parent
        traceback.print_exc(file=sys.stderr)
        response_stream.write(
            json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False) + "\n"
        )
        response_stream.flush()
        return 1

    for line in request_stream:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        response: dict[str, Any] = {}
        try:
            op = request.get("op")
            if op == "reset":
                if hasattr(policy, "reset_policy"):
                    policy.reset_policy()
                response["actions"] = None
            elif op == "act":
                observations = {
                    str(agent): np.asarray(values, dtype=np.float32)
                    for agent, values in request["observations"].items()
                }
                actions = policy.decide_actions(observations)
                response["actions"] = {
                    str(agent): int(value) for agent, value in dict(actions).items()
                }
            else:
                raise ValueError(f"unknown op {op!r}")
        except Exception as exc:  # noqa: BLE001 - reported as data to the parent
            response = {"error": f"{type(exc).__name__}: {exc}"}
            traceback.print_exc(file=sys.stderr)
        response_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
        response_stream.flush()
        if "error" in response:
            break

    response_stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
