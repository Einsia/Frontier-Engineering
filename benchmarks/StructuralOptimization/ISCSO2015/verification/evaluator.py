"""
Evaluator for ISCSO 2015 — 45-Bar 2D Truss Size + Shape Optimization

Scoring contract
----------------
The candidate hands back *design variables only* (``solution_vector``: 45 areas
followed by 9 shape coordinates). Everything that decides the score -- the FEM
solve, the stress/displacement constraint check, the weight, and the score
itself -- is recomputed here from those variables. No field the candidate
reports about its own design is ever believed.

Isolation invariants (see ``benchmarks/_shared/candidate_sandbox.py``)
---------------------------------------------------------------------
1. Every import this module needs is resolved at *module import time*, before
   the candidate has run. ``fem_truss2d`` used to be imported lazily inside
   ``build_fem_and_evaluate`` -- i.e. after the candidate subprocess had
   returned -- so a candidate that restored the write bit on
   ``verification/fem_truss2d.py`` (same uid, so ``chmod`` always succeeds) and
   rewrote it got the scorer to import *its* solver and mint its own weight.
2. The candidate delivers a solution, never a score.
3. A non-zero return code, or a timeout, is a failure. It is not excused by a
   surviving ``submission.json``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

INVALID_COMBINED_SCORE = -1e18

_HERE = Path(__file__).resolve().parent
_BENCHMARK_DIR = _HERE.parent

# --- Invariant 1: resolve every dependency now -------------------------------
# This module is imported by frontier_eval/evaluator.py before any candidate
# code exists in this process, so binding the FEM solver here means the object
# used to score is the one that shipped with the benchmark, whatever the
# candidate later does to the file on disk.
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from fem_truss2d import TrussFEM2D  # noqa: E402

try:  # optional: only present when running under openevolve
    from openevolve.evaluation_result import EvaluationResult as _EvaluationResult
except Exception:  # pragma: no cover - depends on the deployment env
    _EvaluationResult = None


def _find_repo_root(start: Path | None = None) -> Path:
    """Locate the repository root directory."""
    if "FRONTIER_ENGINEERING_ROOT" in os.environ:
        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "frontier_eval").is_dir() and (parent / "benchmarks").is_dir():
            return parent
    return Path.cwd().resolve()


def _locate_shared_dir() -> Path:
    """Find ``benchmarks/_shared``, which lives outside every benchmark tree.

    ``copy_files.txt`` is ``.`` for this benchmark, so the sandbox contains a
    writable copy of the whole benchmark directory. The isolation helper is
    deliberately kept outside it: a candidate can never rewrite the code that
    runs it.
    """
    candidates: list[Path] = []
    env_root = os.environ.get("FRONTIER_ENGINEERING_ROOT", "").strip()
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve() / "benchmarks" / "_shared")
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "benchmarks" / "_shared")
        candidates.append(parent / "_shared")
    for cand in candidates:
        if (cand / "candidate_sandbox.py").is_file():
            return cand
    raise RuntimeError(
        "benchmarks/_shared/candidate_sandbox.py not found; refusing to run a "
        "candidate without process isolation "
        f"(searched: {[str(c) for c in candidates[:8]]})"
    )


sys.path.insert(0, str(_locate_shared_dir()))
import candidate_sandbox as sandbox  # noqa: E402


# Both locations the historical evaluator accepted, most specific first.
_SUBMISSION_RELPATHS = ("temp/submission.json", "submission.json")
_CANDIDATE_TIMEOUT_S = 600.0


def _tail(text: str, limit: int = 8000) -> str:
    return text if len(text) <= limit else text[-limit:]


def load_problem_data(repo_root: Path) -> dict:
    """Load the problem definition JSON.

    Note that ``repo_root`` is the *real* repository root (the harness exports
    ``FRONTIER_ENGINEERING_ROOT``), not the sandbox copy, so the load cases,
    material properties and geometry used for scoring are the pristine ones
    even if the sandbox copy is tampered with.
    """
    candidates = [
        repo_root / "benchmarks" / "StructuralOptimization" / "ISCSO2015"
        / "references" / "problem_data.json",
        repo_root / "StructuralOptimization" / "ISCSO2015"
        / "references" / "problem_data.json",
        _BENCHMARK_DIR / "references" / "problem_data.json",
    ]
    for path in candidates:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(
        f"problem_data.json not found. Searched: {[str(p) for p in candidates]}"
    )


def validate_submission(submission: Any, problem: dict) -> tuple[list[float] | None, str]:
    """Scorer-owned structural check on the candidate's submission.

    Returns ``(solution_vector, "")`` or ``(None, reason)``. This runs before
    any physics so that a malformed payload can never reach the solver, and it
    only ever looks at ``solution_vector`` -- every other key the candidate
    writes (``weight``, ``feasible``, ``max_stress``, ``score``, ...) is
    ignored by construction.
    """
    if not isinstance(submission, dict):
        return None, "submission.json must contain a JSON object"
    if "solution_vector" not in submission:
        return None, "submission.json missing 'solution_vector'"

    raw = submission["solution_vector"]
    if not isinstance(raw, list):
        return None, "'solution_vector' must be a JSON list"

    expected_dim = int(problem["dimension"])
    if len(raw) != expected_dim:
        return None, f"Expected {expected_dim} variables, got {len(raw)}"

    values: list[float] = []
    for i, item in enumerate(raw):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None, f"'solution_vector[{i}]' must be a number, got {type(item).__name__}"
        values.append(float(item))

    return values, ""


def build_fem_and_evaluate(
    solution_vector: list[float], problem: dict
) -> dict[str, Any]:
    """
    Run FEM analysis and check all constraints.

    Parameters
    ----------
    solution_vector : list of float
        Length-54 vector: [A_0..A_44, y_11..y_19].
    problem : dict
        Problem data loaded from JSON.

    Returns
    -------
    result : dict
        Evaluation results including objective, feasibility, violations.
    """
    x = np.array(solution_vector, dtype=float)

    # --- Input validation ---
    expected_dim = problem["dimension"]
    if len(x) != expected_dim:
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": f"Expected {expected_dim} variables, got {len(x)}",
            "score": float("inf"),
        }

    # Check for NaN / Inf
    if not np.all(np.isfinite(x)):
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": "Solution contains NaN or Inf values",
            "score": float("inf"),
        }

    num_bars = problem["num_bars"]
    areas = x[:num_bars]
    shape_vars = x[num_bars:]

    bounds = problem["variable_bounds"]
    a_min, a_max = bounds["area_min"], bounds["area_max"]
    y_min, y_max = bounds["y_min"], bounds["y_max"]

    # Check variable bounds
    if np.any(areas < a_min - 1e-9) or np.any(areas > a_max + 1e-9):
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": f"Area variables out of bounds [{a_min}, {a_max}]",
            "max_area_violation": float(
                max(np.max(a_min - areas), np.max(areas - a_max), 0)
            ),
            "score": float("inf"),
        }

    if np.any(shape_vars < y_min - 1e-9) or np.any(shape_vars > y_max + 1e-9):
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": f"Shape variables out of bounds [{y_min}, {y_max}]",
            "score": float("inf"),
        }

    # Clip to bounds (handle floating-point edge cases)
    areas = np.clip(areas, a_min, a_max)
    shape_vars = np.clip(shape_vars, y_min, y_max)

    # --- Build node coordinates with shape variables ---
    nodes = np.zeros((problem["num_nodes"], 2))
    shape_node_ids = problem["shape_variable_node_ids"]

    for node_data in problem["nodes"]:
        nid = node_data["id"]
        idx = nid - 1
        nodes[idx, 0] = node_data["x"]
        nodes[idx, 1] = node_data["y"]

    # Apply shape variables
    for idx, nid in enumerate(shape_node_ids):
        node_idx = nid - 1
        nodes[node_idx, 1] = shape_vars[idx]

    # --- Build element connectivity ---
    elements = np.array(
        [[b["node_i"] - 1, b["node_j"] - 1] for b in problem["bars"]], dtype=int
    )

    # --- Create FEM solver ---
    E = problem["material"]["E"]
    rho = problem["material"]["rho"]
    supports = problem["supports"]

    try:
        fem = TrussFEM2D(nodes, elements, E, supports)
    except Exception as exc:
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": f"FEM setup failed: {exc}",
            "score": float("inf"),
        }

    # --- Evaluate all load cases ---
    constraints = problem["constraints"]
    sigma_limit = constraints["stress_limit"]
    disp_limit = constraints["displacement_limit"]
    tol = constraints.get("tolerance", 1e-6)

    max_stress_vio = 0.0
    max_disp_vio = 0.0
    all_stresses = []
    all_displacements = []

    for lc in problem["load_cases"]:
        # Build force vector
        force_vec = np.zeros(2 * problem["num_nodes"])
        for load in lc["loads"]:
            nid = load["node"]
            idx = nid - 1
            force_vec[2 * idx] += load["fx"]
            force_vec[2 * idx + 1] += load["fy"]

        try:
            displacements, stresses, lengths = fem.solve(areas, force_vec)
        except Exception as exc:
            return {
                "objective": float("inf"),
                "feasible": False,
                "error": f"FEM solve failed for LC {lc['id']}: {exc}",
                "score": float("inf"),
            }

        # Check stress constraints
        abs_stresses = np.abs(stresses)
        stress_violations = abs_stresses - sigma_limit
        lc_max_stress_vio = float(np.max(stress_violations))
        max_stress_vio = max(max_stress_vio, lc_max_stress_vio)

        # Check displacement constraints (absolute value of each DOF)
        abs_disp = np.abs(displacements)
        disp_violations = abs_disp - disp_limit
        lc_max_disp_vio = float(np.max(disp_violations))
        max_disp_vio = max(max_disp_vio, lc_max_disp_vio)

        all_stresses.append(stresses.tolist())
        all_displacements.append(displacements.tolist())

    # --- Compute objective ---
    weight = fem.compute_weight(areas, rho)

    # --- Feasibility (a hard gate, never a penalty multiplier) ---
    feasible = (max_stress_vio <= tol) and (max_disp_vio <= tol)

    return {
        "objective": float(weight),
        "feasible": bool(feasible),
        "max_stress_violation": float(max(max_stress_vio, 0.0)),
        "max_displacement_violation": float(max(max_disp_vio, 0.0)),
        "score": float(weight) if feasible else float("inf"),
        "num_load_cases": len(problem["load_cases"]),
    }


def _stage_inputs(repo_root: Path) -> dict[str, Any]:
    """Read-only copies the candidate is allowed to see inside its sandbox."""
    inputs: dict[str, Any] = {}
    refs = [
        repo_root / "benchmarks" / "StructuralOptimization" / "ISCSO2015" / "references",
        repo_root / "StructuralOptimization" / "ISCSO2015" / "references",
        _BENCHMARK_DIR / "references",
    ]
    for refs_dir in refs:
        src = refs_dir / "problem_data.json"
        if src.is_file():
            inputs["references/problem_data.json"] = src
            break
    # Empty placeholders at both accepted submission paths. `expected_outputs`
    # treats a missing file as a hard error, and we want to accept either
    # location; a placeholder that the candidate never wrote stays zero bytes
    # and is read back as "not produced".
    for rel in _SUBMISSION_RELPATHS:
        inputs[rel] = b""
    return inputs


def _pick_submission_bytes(run: "sandbox.IsolatedRun") -> tuple[bytes | None, str]:
    for rel in _SUBMISSION_RELPATHS:
        try:
            raw = run.read_output_bytes(rel)
        except KeyError:
            continue
        if raw.strip():
            return raw, rel
    return None, ""


def evaluate(program_path: str, *, repo_root: Path | None = None) -> Any:
    """
    Full evaluation pipeline:
    1. Run the candidate in an isolated subprocess; it may only produce data
    2. Validate the submission's shape (scorer-owned, before any physics)
    3. Run this process's own FEM + constraint check on the design variables
    4. Compute the score here from that result

    Parameters
    ----------
    program_path : str
        Path to the candidate Python program.
    repo_root : Path, optional
        Repository root. Auto-detected if not given.
    """
    start = time.time()
    repo_root = (
        _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    )
    program_path_resolved = Path(program_path).expanduser().resolve()

    artifacts: dict[str, str] = {}

    metrics: dict[str, float] = {
        "combined_score": INVALID_COMBINED_SCORE,
        "weight_kg": 0.0,
        "valid": 0.0,
        "feasible": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }

    # 1. Problem data is loaded *before* the candidate runs and never re-read
    #    afterwards, so the geometry, load cases, material and limits used for
    #    scoring cannot be influenced by anything the candidate writes.
    problem = load_problem_data(repo_root)

    try:
        run = sandbox.run_candidate_isolated(
            program_path_resolved,
            inputs=_stage_inputs(repo_root),
            expected_outputs=_SUBMISSION_RELPATHS,
            timeout_s=_CANDIDATE_TIMEOUT_S,
            # Run from a copy in a scratch directory: the candidate's __file__
            # then points into the scratch dir, not into the sandboxed benchmark
            # tree, so it cannot reach verification/ or references/ that way.
            copy_into_workdir=True,
        )
    except sandbox.InvalidSubmissionError as exc:
        artifacts["error_message"] = str(exc)
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    artifacts["program_stdout"] = _tail(run.stdout_tail)
    artifacts["program_stderr"] = _tail(run.stderr_tail)
    # Kept for backward compatibility with consumers of the old keys; the
    # isolation helper only hands back the last 8000 chars of each stream.
    artifacts["program_stdout_full"] = artifacts["program_stdout"]
    artifacts["program_stderr_full"] = artifacts["program_stderr"]
    artifacts["program_output_truncated"] = "tail-8000"
    metrics["program_returncode"] = float(run.returncode)
    metrics["candidate_runtime_s"] = float(run.runtime_s)

    # 2. Invariant 3: a crash or a timeout is a failure, full stop.
    if run.timed_out:
        metrics["timeout"] = 1.0
        metrics["runtime_s"] = float(time.time() - start)
        artifacts["error_message"] = f"program timeout after {_CANDIDATE_TIMEOUT_S}s"
        return _wrap(metrics, artifacts)

    if run.returncode != 0:
        metrics["runtime_s"] = float(time.time() - start)
        artifacts["error_message"] = (
            f"program exited non-zero (returncode={run.returncode}); "
            "a surviving submission.json does not excuse a crash"
        )
        return _wrap(metrics, artifacts)

    # 3. Read submission
    raw, rel = _pick_submission_bytes(run)
    if raw is None:
        artifacts["error_message"] = (
            "submission.json not generated "
            "(checked temp/submission.json and submission.json)"
        )
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    artifacts["submission_path"] = rel

    try:
        submission = json.loads(raw.decode("utf-8"))
        artifacts["submission.json"] = json.dumps(submission, indent=2)
    except Exception as exc:
        artifacts["error_message"] = f"Failed to parse submission.json: {exc}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    solution_vector, reason = validate_submission(submission, problem)
    if solution_vector is None:
        artifacts["error_message"] = reason
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    if isinstance(submission, dict):
        ignored = sorted(k for k in submission if k != "solution_vector")
        if ignored:
            artifacts["ignored_submission_fields"] = ", ".join(ignored)

    # 4. Score, recomputed here from the design variables alone.
    result = build_fem_and_evaluate(solution_vector, problem)
    artifacts["evaluation_result"] = json.dumps(result, indent=2)

    runtime_s = time.time() - start
    metrics["weight_kg"] = result.get("objective", 0.0)
    metrics["runtime_s"] = float(runtime_s)
    metrics["feasible"] = 1.0 if result.get("feasible", False) else 0.0
    metrics["max_stress_violation"] = result.get("max_stress_violation", 0.0)
    metrics["max_displacement_violation"] = result.get(
        "max_displacement_violation", 0.0
    )

    if result.get("feasible", False):
        # Minimization: negate weight so higher combined_score = better
        metrics["combined_score"] = -float(result["objective"])
        metrics["valid"] = 1.0
    else:
        # Invalid: large negative so it's always worse than any feasible solution
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["valid"] = 0.0

    return _wrap(metrics, artifacts)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]) -> Any:
    if _EvaluationResult is None:
        # Without openevolve there is no EvaluationResult to return. Returning a
        # bare metrics dict silently threw the artifacts away, because
        # run_eval._normalize_result only unpacks a dict that carries a
        # "metrics" key -- which is how the error messages, the submission and
        # the num_evaluations "unverified" notice all went missing on hosts
        # that do not have openevolve installed.
        return {"metrics": metrics, "artifacts": artifacts}
    return _EvaluationResult(metrics=metrics, artifacts=artifacts)


if __name__ == "__main__":
    # Standalone test: evaluate a submission directly
    if len(sys.argv) < 2:
        print("Usage: python evaluator.py <program_path>")
        print("  or:  python evaluator.py --test <submission.json>")
        sys.exit(1)

    if sys.argv[1] == "--test" and len(sys.argv) >= 3:
        # Direct evaluation mode (no subprocess)
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            sub = json.load(f)
        repo = _find_repo_root()
        prob = load_problem_data(repo)
        result = build_fem_and_evaluate(sub["solution_vector"], prob)
        print(json.dumps(result, indent=2))
    else:
        result = evaluate(sys.argv[1])
        if hasattr(result, "metrics"):
            output = {"metrics": result.metrics, "artifacts": result.artifacts}
        else:
            output = result
        print(json.dumps(output, indent=2))
