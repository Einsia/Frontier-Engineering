from __future__ import annotations

import json
import math
import os
import sys
import time
import traceback
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

CANDIDATE_TIMEOUT_S = 300.0

# Submission bounds owned by the scorer. `verification/evaluator.py` reads every
# detector field with `.get(..., 0.0)`, so a missing or non-numeric field used to
# be silently replaced by a zero rather than rejected.
MAX_DETECTORS = 15
COORD_ABS_LIMIT = 1e6
ANGLE_ABS_LIMIT = 1e6
DETECTOR_FIELDS = ("x", "y", "z", "theta", "phi")

CANDIDATE_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
CANDIDATE_RLIMITS = {"FSIZE": 1 << 30, "NOFILE": 4096}


def _is_repo_root(path: Path) -> bool:
    if not (path / "frontier_eval").is_dir():
        return False
    return (path / "benchmarks").is_dir()


def _find_repo_root() -> Path:
    if "FRONTIER_ENGINEERING_ROOT" in os.environ:
        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            return parent
    return Path.cwd().resolve()


def _import_isolation(repo_root: Path):
    """Import the shared candidate-isolation helper.

    It sits outside every benchmark directory so a ``copy_files.txt`` of ``.``
    cannot drag it into a sandbox the candidate can write to.
    """
    shared = repo_root / "benchmarks" / "_shared"
    if not (shared / "candidate_sandbox.py").is_file():
        raise RuntimeError(f"shared isolation helper not found under {shared}")
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import candidate_sandbox  # noqa: PLC0415

    return candidate_sandbox


def _load_scoring_module(repo_root: Path) -> Any:
    """Load scoring functions and their dependencies before candidate execution.
    """
    path = (
        repo_root
        / "benchmarks"
        / "ParticlePhysics"
        / "MuonTomography"
        / "verification"
        / "evaluator.py"
    ).resolve()
    if not path.is_file():
        raise RuntimeError(f"scoring module not found: {path}")
    spec = spec_from_file_location("_muon_scoring", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load scoring module: {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "evaluate_solution"):
        raise RuntimeError(f"scoring module defines no evaluate_solution(): {path}")
    return module


def _tail(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _validate_solution(data: Any) -> tuple[dict | None, str | None]:
    """Strict, scorer-owned checks on the candidate's reported solution."""
    if not isinstance(data, dict):
        return None, "solution.json must contain a JSON object"

    detectors = data.get("detectors")
    if not isinstance(detectors, list):
        return None, "solution.json must contain a 'detectors' list"
    if not detectors:
        return None, "detector list is empty"
    if len(detectors) > MAX_DETECTORS:
        return None, f"too many detectors: {len(detectors)} > {MAX_DETECTORS}"

    clean: list[dict[str, float]] = []
    for i, det in enumerate(detectors):
        if not isinstance(det, dict):
            return None, f"detector {i} is not an object"
        row: dict[str, float] = {}
        for field in DETECTOR_FIELDS:
            if field not in det:
                return None, f"detector {i} is missing '{field}'"
            value = det[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None, f"detector {i} field '{field}' must be a number"
            value = float(value)
            if not math.isfinite(value):
                return None, f"detector {i} field '{field}' must be finite"
            limit = COORD_ABS_LIMIT if field in ("x", "y", "z") else ANGLE_ABS_LIMIT
            if abs(value) > limit:
                return None, f"detector {i} field '{field}' out of range: {value}"
            row[field] = value
        clean.append(row)

    return {"detectors": clean}, None


def evaluate(program_path: str, *, repo_root: Path | None = None):
    """
    Evaluator for benchmarks/ParticlePhysics/MuonTomography.

    - Runs the candidate in an isolated subprocess whose only output is
      `solution.json` -- detector placements, never a score.
    - Validates that submission against scorer-owned bounds.
    - Recomputes the score in this process with `verification/evaluator.py`'s
      `evaluate_solution`, which was imported *before* the candidate ran.
    """
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program_path = Path(program_path).expanduser().resolve()

    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }
    artifacts: dict[str, str] = {}

    # Both the isolation helper and the scoring code are resident before any
    # candidate code executes.
    try:
        sandbox = _import_isolation(repo_root)
        scoring = _load_scoring_module(repo_root)
    except Exception as e:
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = _tail(traceback.format_exc())
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    try:
        run = sandbox.run_candidate_isolated(
            program_path,
            expected_outputs=("solution.json",),
            timeout_s=CANDIDATE_TIMEOUT_S,
            copy_into_workdir=True,
            env_allowlist=CANDIDATE_ENV_ALLOWLIST,
            rlimits=CANDIDATE_RLIMITS,
            python=sys.executable,
        )
    except sandbox.InvalidSubmissionError as e:
        artifacts["error_message"] = f"solution.json not generated: {e}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    except Exception as e:
        artifacts["error_message"] = f"failed to run candidate: {e}"
        artifacts["traceback"] = _tail(traceback.format_exc())
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    artifacts["program_stdout"] = _tail(run.stdout_tail)
    artifacts["program_stderr"] = _tail(run.stderr_tail)
    metrics["program_returncode"] = float(run.returncode)

    if run.timed_out:
        artifacts["error_message"] = f"program timeout after {CANDIDATE_TIMEOUT_S}s"
        metrics["timeout"] = 1.0
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    if run.returncode != 0:
        artifacts["error_message"] = f"candidate program exited non-zero ({run.returncode})"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    raw = run.read_output_bytes("solution.json")
    artifacts["solution.json"] = _tail(raw.decode("utf-8", errors="replace"))
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as e:
        artifacts["error_message"] = f"solution.json is not valid JSON: {e}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    solution, error = _validate_solution(parsed)
    if solution is None:
        artifacts["error_message"] = f"invalid solution.json: {error}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    try:
        result = scoring.evaluate_solution(solution)
    except Exception as e:
        artifacts["error_message"] = f"scoring failed: {e}"
        artifacts["traceback"] = _tail(traceback.format_exc())
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    score = float(result.get("score", 0.0))
    if not math.isfinite(score):
        artifacts["error_message"] = f"scoring produced a non-finite score: {score}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    detail = result.get("metrics") or {}
    for key in ("total_signal", "total_cost", "valid_detectors"):
        if key in detail:
            try:
                metrics[key] = float(detail[key])
            except Exception:
                pass
    artifacts["score_breakdown"] = json.dumps(result, ensure_ascii=False, indent=2, default=str)

    metrics["combined_score"] = score
    metrics["valid"] = 1.0 if score > 0.0 else 0.0
    metrics["runtime_s"] = float(time.time() - start)
    return _wrap(metrics, artifacts)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
