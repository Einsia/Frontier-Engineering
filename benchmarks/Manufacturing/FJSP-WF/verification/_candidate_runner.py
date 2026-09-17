"""Candidate runner - subprocess helper for FJSP-WF evaluator."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def run_candidate(candidate_path: Path, instance: dict[str, Any]) -> dict[str, Any]:
    """Dynamically import and execute a candidate solver on one instance."""
    spec = importlib.util.spec_from_file_location("fjspwf_candidate", candidate_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {candidate_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["fjspwf_candidate"] = module
    spec.loader.exec_module(module)
    return module.solve_instance(instance)


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: _candidate_runner.py candidate_path"}))
        sys.exit(1)

    candidate_path = Path(sys.argv[1]).resolve()
    if not candidate_path.is_file():
        print(json.dumps({"error": f"Candidate file not found: {candidate_path}"}))
        sys.exit(1)

    try:
        instance = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid instance JSON on stdin: {exc}"}))
        sys.exit(1)

    try:
        result = run_candidate(candidate_path, instance)
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({"error": f"Candidate execution failed: {exc}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
