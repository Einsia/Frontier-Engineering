"""Shared scorer-side execution for the Optics ``fiber_*`` benchmarks.

The candidate runs from a temporary workspace containing the runner, solver
and scenario data. It returns declared solution fields in ``submission.json``;
the scorer validates them and recomputes the metrics. Nonzero exits, timeouts,
missing output and nonfinite values are rejected.

Callers import scoring dependencies before executing candidates. The temporary
workspace removes ``verification/`` from the default Python import path. This
helper uses compatibility mode: the PID namespace does not hide host files,
so it does not by itself prevent reading scorer files or private oracle data.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

__all__ = [
    "FiberTaskContract",
    "load_module_from_path",
    "run_candidate",
    "invalid_summary",
    "write_summary",
    "run_task",
    "ARRAY_TAG",
]

ARRAY_TAG = "__ndarray__"

_SHARED_DIR = Path(__file__).resolve().parent
RUNNER_PATH = _SHARED_DIR / "candidate_runner.py"


def _find_repo_root() -> Path:
    """Locate the repo root.

    In the unified sandbox the benchmark tree is copied to a temp directory, so
    walking up from ``__file__`` finds nothing; the harness exports
    ``FRONTIER_ENGINEERING_ROOT`` (remapped to the container path under docker
    isolation) for precisely this case.
    """
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / "benchmarks" / "_shared").is_dir():
            return candidate
    for parent in _SHARED_DIR.parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    raise RuntimeError("could not locate repo root for the Optics fiber harness")


_REPO = _find_repo_root()
_SANDBOX_DIR = str(_REPO / "benchmarks" / "_shared")
if _SANDBOX_DIR not in sys.path:
    sys.path.insert(0, _SANDBOX_DIR)

import candidate_sandbox as sandbox  # noqa: E402


# --------------------------------------------------------------------------
# scenario serialisation
# --------------------------------------------------------------------------


def _encode(obj: Any) -> Any:
    """Encode a scenario value as JSON, tagging numpy arrays so the child can
    rebuild them and the candidate sees exactly the types it saw in-process."""
    import numpy as np

    if isinstance(obj, np.ndarray):
        return {ARRAY_TAG: obj.tolist(), "dtype": str(obj.dtype)}
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {str(k): _encode(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_encode(v) for v in obj]
    if isinstance(obj, (str, bool, int, float)) or obj is None:
        return obj
    raise TypeError(f"scenario value of type {type(obj).__name__} is not serialisable")


# --------------------------------------------------------------------------
# solution validation (shape / type / finiteness), before any task-specific check
# --------------------------------------------------------------------------


def _check_numeric_tree(value: Any, path: str, errors: list[str], depth: int = 0) -> None:
    if isinstance(value, bool):
        errors.append(f"{path} must be numeric, got a bool")
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            errors.append(f"{path} must be finite, got {value!r}")
        return
    if isinstance(value, list):
        if depth >= 3:
            errors.append(f"{path} is nested too deeply")
            return
        if len(value) > 100_000:
            errors.append(f"{path} is too large ({len(value)} entries)")
            return
        for i, item in enumerate(value):
            _check_numeric_tree(item, f"{path}[{i}]", errors, depth + 1)
        return
    errors.append(f"{path} must be a number or a list of numbers, got {type(value).__name__}")


def _validate_solution(payload: Any, keys: Sequence[str]) -> tuple[dict | None, str | None]:
    if not isinstance(payload, dict):
        return None, "submission.json must contain a JSON object"
    solution = payload.get("solution")
    if not isinstance(solution, dict):
        return None, "submission.json must contain a 'solution' object"

    errors: list[str] = []
    kept: dict[str, Any] = {}
    for key in keys:
        if key not in solution:
            errors.append(f"solution is missing required key '{key}'")
            continue
        value = solution[key]
        _check_numeric_tree(value, f"solution['{key}']", errors, depth=0)
        kept[key] = value

    if errors:
        return None, "; ".join(errors[:8])
    # Only the declared solution keys survive. Anything else the candidate
    # reported (a score, an "is_valid" flag, oracle metadata) is dropped here so
    # it cannot reach the scorer.
    return kept, None


# --------------------------------------------------------------------------
# contract + runner
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FiberTaskContract:
    """Everything the harness needs to drive one fiber task's candidate."""

    task_name: str
    entrypoint: str
    solution_keys: tuple[str, ...]
    # Scenario keys handed to the candidate. ``None`` means "the whole
    # scenario", matching the old ``fn(**scenario)`` call.
    solver_kwargs: tuple[str, ...] | None = None
    # Keys the in-process contract delivered as a tuple (not an array).
    tuple_kwargs: tuple[str, ...] = ()
    timeout_s: float = 120.0


def _child_env_allowlist() -> tuple[str, ...]:
    """Inherit the parent environment except the pointers back at the task tree.

    ``FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR`` / ``..._BENCHMARK_DIR`` /
    ``FRONTIER_ENGINEERING_ROOT`` would each hand a candidate the absolute path
    of a directory containing ``verification/oracle.py``. Everything else
    (PATH, HOME, VIRTUAL_ENV, PYTHONPATH...) is kept so the child can still
    import numpy from the same interpreter the scorer uses.

    ``PYTHONDONTWRITEBYTECODE`` is forced on so importing the candidate does not
    leave a ``__pycache__`` behind in the sandbox: the sandbox should hold
    exactly the three files we put there, and nothing that outlives the run.
    """
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    return tuple(k for k in os.environ if not k.startswith("FRONTIER_"))


def run_candidate(
    contract: FiberTaskContract,
    candidate_path: Path,
    scenario: dict,
) -> tuple[dict | None, str | None]:
    """Run the candidate in its own process; return ``(solution, error)``."""
    candidate_path = Path(candidate_path)
    if not candidate_path.is_file():
        return None, f"candidate not found: {candidate_path}"
    if not RUNNER_PATH.is_file():
        return None, f"candidate runner missing: {RUNNER_PATH}"

    names = contract.solver_kwargs if contract.solver_kwargs is not None else tuple(scenario)
    missing = [k for k in names if k not in scenario]
    if missing:
        return None, f"scenario is missing keys {missing} (evaluator bug)"

    try:
        scenario_bytes = json.dumps(
            {
                "kwargs": {k: _encode(scenario[k]) for k in names},
                "tuple_kwargs": list(contract.tuple_kwargs),
            },
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        return None, f"failed to serialise scenario: {exc}"

    try:
        run = sandbox.run_candidate_isolated(
            RUNNER_PATH,
            inputs={
                "scenario.json": scenario_bytes,
                "candidate_solver.py": candidate_path.resolve(),
            },
            expected_outputs=("submission.json",),
            timeout_s=float(contract.timeout_s),
            argv=("--entrypoint", contract.entrypoint),
            # Copy the runner into the temporary cwd so verification/ is not
            # on the default Python import path. Host files remain visible.
            copy_into_workdir=True,
            env_allowlist=_child_env_allowlist(),
            rlimits={"CPU": int(contract.timeout_s) + 30},
        )
    except sandbox.InvalidSubmissionError as exc:
        return None, str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"failed to run candidate: {exc}"

    if run.timed_out:
        return None, f"candidate timed out after {contract.timeout_s:g}s"
    if run.returncode != 0:
        tail = (run.stderr_tail or "").strip().splitlines()[-1:] or [""]
        return None, f"candidate exited non-zero ({run.returncode}): {tail[0][:400]}"

    try:
        payload = sandbox.load_json_output(run)
    except sandbox.InvalidSubmissionError as exc:
        return None, str(exc)

    return _validate_solution(payload, contract.solution_keys)


# --------------------------------------------------------------------------
# misc helpers shared by the four evaluators
# --------------------------------------------------------------------------


def load_module_from_path(name: str, path: Path):
    """Import a scorer-side module by absolute path.

    Used for ``verification/oracle.py`` so the evaluators no longer depend on
    ``sys.path`` containing the directory the candidate used to live in.
    """
    spec = importlib.util.spec_from_file_location(name, Path(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def invalid_summary(error: str) -> dict:
    """The summary shape ``frontier_eval/parse_result.py`` reads as invalid.

    ``_extract_fiber`` falls back to the top-level ``is_valid`` when there is no
    ``candidate`` section, which drives ``valid=0`` and the harness-wide
    INVALID_COMBINED_SCORE sentinel.
    """
    return {"is_valid": False, "score": 0.0, "error": str(error)}


def write_summary(out_dir: Path, summary: dict) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )


def run_task(
    *,
    contract: FiberTaskContract,
    candidate_path: Path,
    out_dir: Path,
    scenario: dict,
    check_valid_output: Callable[[dict], tuple[bool, str]],
    evaluate: Callable[[dict, dict], dict],
    oracle_result: Callable[[dict], dict],
    save_plot: Callable[[dict, dict, dict, Path], None] | None = None,
    plot_name: str = "verification.png",
) -> dict:
    """One shared main() body for all four fiber evaluators.

    ``evaluate`` and ``oracle_result`` are the task's own scoring code; they are
    called only on data, never on anything the candidate can execute here.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    solution, error = run_candidate(contract, Path(candidate_path), scenario)
    if solution is None:
        summary = invalid_summary(error or "candidate rejected")
        write_summary(out_dir, summary)
        print(json.dumps(summary, indent=2))
        return summary

    try:
        ok, msg = check_valid_output(solution)
    except Exception as exc:
        ok, msg = False, f"solution rejected while checking: {exc}"
    if not ok:
        summary = invalid_summary(msg)
        write_summary(out_dir, summary)
        print(json.dumps(summary, indent=2))
        return summary

    try:
        cand = evaluate(solution, scenario)
    except Exception as exc:
        summary = invalid_summary(f"solution rejected while scoring: {exc}")
        write_summary(out_dir, summary)
        print(json.dumps(summary, indent=2))
        return summary

    oracle_r = oracle_result(scenario)
    oracle_e = evaluate(oracle_r, scenario)
    oracle_meta = oracle_r.get("__oracle_meta__", {}) if isinstance(oracle_r, dict) else {}

    summary = {
        "candidate": cand,
        "oracle": oracle_e,
        "oracle_meta": oracle_meta,
        "score_gap_oracle_minus_candidate": float(oracle_e["score"] - cand["score"]),
    }

    if save_plot is not None:
        try:
            save_plot(cand, oracle_e, scenario, out_dir / plot_name)
        except Exception as exc:  # a plotting failure must not void a real score
            summary["plot_error"] = str(exc)

    write_summary(out_dir, summary)
    print(json.dumps(summary, indent=2))
    return summary
