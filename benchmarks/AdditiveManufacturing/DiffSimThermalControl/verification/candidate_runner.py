"""Trusted child-process entrypoint for the DiffSimThermalControl candidate.

The evaluator never imports the candidate. Instead it runs *this* file in a
throw-away subprocess (see ``benchmarks/_shared/candidate_sandbox.py``) with the
candidate path as ``argv[1]``. This module:

* reads the case list the evaluator prepared (``cases.json`` in the cwd), so the
  child cannot influence which cases are scored;
* imports ``verification/canonical.py`` by absolute path *before* the candidate
  is imported, so the candidate's module-level code cannot swap the simulator
  the search loop uses;
* calls ``solve(case, max_sim_calls=..., simulate_fn=...)`` once per case and
  writes only *data* (the control knots plus a call count) to ``submission.json``.

Nothing written here is authority: the evaluator re-runs ``canonical.simulate``
on the returned knots in its own pristine process and recomputes the score.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any

RUNNER_DIR = Path(__file__).resolve().parent
CASES_INPUT = "cases.json"
SUBMISSION_OUTPUT = "submission.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _extract_params(result: Any) -> list[float]:
    if not isinstance(result, dict):
        raise ValueError("candidate solve() must return a dictionary")
    if "params" not in result:
        raise ValueError("candidate result must contain key 'params'")
    return [float(value) for value in result["params"]]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: candidate_runner.py <candidate.py> [max_sim_calls]", file=sys.stderr)
        return 2
    candidate_path = Path(sys.argv[1]).expanduser().resolve()
    max_sim_calls = int(sys.argv[2]) if len(sys.argv) > 2 else 24

    payload = json.loads(Path(CASES_INPUT).read_text(encoding="utf-8"))
    cases = payload["cases"]

    # Bind the canonical simulator before any candidate code exists in this
    # process; a later monkeypatch of sys.modules cannot reach this reference.
    canonical = _load_module("am_canonical_child", RUNNER_DIR / "canonical.py")
    canonical_simulate = canonical.simulate

    candidate = _load_module("am_candidate", candidate_path)
    solve = getattr(candidate, "solve", None)
    if not callable(solve):
        raise AttributeError(
            "candidate must define solve(case, max_sim_calls=..., simulate_fn=...)"
        )

    results: list[dict[str, Any]] = []
    for case in cases:
        state = {"calls": 0}

        def counted_simulate(
            params: Any,
            sim_case: Any,
            _simulate=canonical_simulate,
            _state=state,
            _budget=max_sim_calls,
        ) -> dict[str, Any]:
            _state["calls"] += 1
            if _state["calls"] > _budget:
                raise RuntimeError(
                    f"simulate_fn budget exceeded: {_state['calls']} > {_budget}"
                )
            return _simulate(params, sim_case)

        entry: dict[str, Any] = {"case_id": case["case_id"]}
        try:
            result = solve(case, max_sim_calls=max_sim_calls, simulate_fn=counted_simulate)
            entry["params"] = _extract_params(result)
        except Exception as exc:  # noqa: BLE001 - reported as data to the parent
            entry["error"] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc(file=sys.stderr)
        entry["sim_calls"] = int(state["calls"])
        results.append(entry)

    Path(SUBMISSION_OUTPUT).write_text(
        json.dumps({"cases": results}, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
