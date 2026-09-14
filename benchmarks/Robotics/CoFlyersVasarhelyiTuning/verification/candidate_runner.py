"""Trusted child-process entrypoint for the CoFlyersVasarhelyiTuning candidate.

The evaluator never imports the candidate. This module runs in a throw-away
subprocess: it reads the case problems the evaluator prepared (``problems.json``
in the cwd), calls the candidate's ``solve(problem)`` once per case, and writes
back only the raw JSON-able value each call returned. No validation, merging,
clipping, or scoring happens here -- the evaluator (which the candidate never
runs inside of) owns all of that once this process exits.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any

PROBLEMS_INPUT = "problems.json"
SUBMISSION_OUTPUT = "submission.json"


def _load_candidate(path: Path):
    spec = importlib.util.spec_from_file_location("coflyers_candidate", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load candidate module from {path}")
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

    problems = json.loads(Path(PROBLEMS_INPUT).read_text(encoding="utf-8"))["problems"]

    candidate = _load_candidate(candidate_path)
    solve_fn = getattr(candidate, "solve", None)
    if not callable(solve_fn):
        raise AttributeError("candidate module must define solve(problem)")

    results: list[dict[str, Any]] = []
    for problem in problems:
        entry: dict[str, Any] = {"case_id": problem["case_id"]}
        try:
            submission = solve_fn(problem)
            if not isinstance(submission, dict):
                raise TypeError(f"solve(problem) must return a dict, got {type(submission)!r}")
            entry["submission"] = _jsonable(submission)
        except Exception as exc:  # noqa: BLE001 - reported as data to the parent
            entry["error"] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc(file=sys.stderr)
        results.append(entry)

    Path(SUBMISSION_OUTPUT).write_text(
        json.dumps({"cases": results}, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
