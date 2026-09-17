"""Isolated JSON-lines worker for causal pump controllers."""

import json
import math
import sys
from pathlib import Path

SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "float": float, "int": int, "len": len,
    "list": list, "max": max, "min": min, "pow": pow, "range": range,
    "reversed": reversed, "round": round, "set": set, "sorted": sorted,
    "str": str, "sum": sum, "tuple": tuple, "zip": zip,
    "Exception": Exception, "ValueError": ValueError,
}


def _load_control(path):
    source = Path(path).read_text(encoding="utf-8")
    namespace = {"__builtins__": SAFE_BUILTINS, "__name__": "candidate", "math": math}
    exec(compile(source, "candidate.py", "exec"), namespace, namespace)
    control = namespace.get("control")
    if not callable(control):
        raise ValueError("candidate must define control(observation)")
    return control


def main():
    try:
        control = _load_control(sys.argv[1])
        print(json.dumps({"ready": True}), flush=True)
    except Exception as exc:
        print(json.dumps({"ready": False, "error": f"{type(exc).__name__}: {exc}"}), flush=True)
        return 2
    for line in sys.stdin:
        try:
            action = control(json.loads(line))
            print(json.dumps({"ok": True, "action": action}, allow_nan=False), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
