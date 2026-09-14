"""Evaluator for ISCSO2023.

The candidate returns 284 section IDs from the fixed section database. The scorer computes
tower response under all load cases, constraints, weight and score from those design variables.
Scoring dependencies are imported before candidate execution. Timeouts and
nonzero exits are rejected even when a submission file exists.

``num_evaluations`` is self-reported; see ``_MAX_EVAL_NOTE``.
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
# code exists in this process, so the solver bound here is the one that shipped
# with the benchmark, whatever the candidate later does to the file on disk.
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from fem_truss3d import TrussFEM3D, generate_tower_topology  # noqa: E402

try:  # optional: only present when running under openevolve
    from openevolve.evaluation_result import EvaluationResult as _EvaluationResult
except Exception:  # pragma: no cover - depends on the deployment env
    # Falling back to a plain metrics dict. This used to be an unguarded import
    # at the bottom of _wrap(), which meant that on a host without openevolve
    # every single run -- honest or not -- raised ModuleNotFoundError out of
    # evaluate() and was recorded as INVALID. A missing optional reporting
    # dependency must never decide whether a submission is valid.
    _EvaluationResult = None


_MAX_EVAL_NOTE = (
    "num_evaluations is reported by the candidate and cannot be verified by "
    "this evaluator: the candidate runs in its own process and nothing forces "
    "its internal FEM calls through us. The budget gate below is kept because "
    "it still rejects an honestly-reported overrun, but a candidate that "
    "under-reports passes it. Treat this metric as unverified."
)

# Both locations the historical evaluator accepted, most specific first.
_SUBMISSION_RELPATHS = ("temp/submission.json", "submission.json")
_CANDIDATE_TIMEOUT_S = 1200.0


def _find_repo_root(start: Path | None = None) -> Path:
    if "FRONTIER_ENGINEERING_ROOT" in os.environ:
        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "frontier_eval").is_dir() and (parent / "benchmarks").is_dir():
            return parent
    return Path.cwd().resolve()


def _locate_shared_dir() -> Path:
    """Find ``benchmarks/_shared``, which lives outside every benchmark tree.

    ``copy_files.txt`` is ``.`` for this benchmark, so the sandbox holds a
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


def _tail(text: str, limit: int = 8000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _references_dir(repo_root: Path) -> Path | None:
    for refs in (
        repo_root / "benchmarks" / "StructuralOptimization" / "ISCSO2023" / "references",
        repo_root / "StructuralOptimization" / "ISCSO2023" / "references",
        _BENCHMARK_DIR / "references",
    ):
        if (refs / "problem_data.json").is_file():
            return refs
    return None


def load_problem_data(repo_root: Path) -> dict | None:
    """Load the pristine problem definition.

    ``repo_root`` is the *real* repository root (the harness exports
    ``FRONTIER_ENGINEERING_ROOT``), not the sandbox copy, so the topology
    parameters, load cases, material and limits used for scoring are the
    pristine ones even if the sandbox copy is tampered with.
    """
    refs = _references_dir(repo_root)
    if refs is None:
        return None
    with open(refs / "problem_data.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_section_database(repo_root: Path, problem: dict | None = None) -> dict[int, float] | None:
    if problem and "section_database" in problem and "sections" in problem["section_database"]:
        return {s["id"]: s.get("area_mm2", s.get("area_cm2", 0.0) * 100) for s in problem["section_database"]["sections"]}
    refs = _references_dir(repo_root)
    if refs is not None and (refs / "section_database.json").is_file():
        with open(refs / "section_database.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            if "sections" in data:
                return {s["id"]: s.get("area_mm2", s.get("area_cm2", 0.0) * 100) for s in data["sections"]}
    return None


def validate_submission(submission: Any, problem: dict) -> tuple[list[float] | None, str]:
    """Scorer-owned structural check, run before any physics.

    Only ``solution_vector`` is consumed. Every other key the candidate writes
    (``weight``, ``feasible``, ``max_stress``, ``score``, ...) is ignored by
    construction; ``num_evaluations`` is read only by the budget gate, which is
    explicitly marked unverified.
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
    solution_vector: list[float], problem: dict, repo_root: Path | None = None
) -> dict[str, Any]:
    x = np.array(solution_vector, dtype=float)
    expected_dim = problem["dimension"]
    if len(x) != expected_dim:
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": f"Expected {expected_dim} variables, got {len(x)}",
            "score": float("inf"),
        }

    if not np.all(np.isfinite(x)):
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": "Solution contains NaN or Inf values",
            "score": float("inf"),
        }

    bounds = problem["variable_bounds"]

    if bounds.get("discrete", False):
        if repo_root is None:
            repo_root = _find_repo_root()
        section_db = load_section_database(repo_root, problem)
        if section_db is None or len(section_db) == 0:
            return {
                "objective": float("inf"),
                "feasible": False,
                "error": "Section database not found or empty",
                "score": float("inf"),
            }
        section_ids = np.round(x).astype(int)
        id_min, id_max = bounds["section_id_min"], bounds["section_id_max"]

        if np.any(section_ids < id_min) or np.any(section_ids > id_max):
            return {
                "objective": float("inf"),
                "feasible": False,
                "error": f"Section IDs must be in [{id_min}, {id_max}], got range [{section_ids.min()}, {section_ids.max()}]",
                "score": float("inf"),
            }

        areas = np.array([section_db.get(sid, 0.0) for sid in section_ids], dtype=float)
        if np.any(areas == 0.0):
            invalid_ids = [sid for sid in section_ids if sid not in section_db]
            return {
                "objective": float("inf"),
                "feasible": False,
                "error": f"Invalid section IDs: {invalid_ids}",
                "score": float("inf"),
            }
    else:
        # Continuous: use areas directly
        areas = x
        a_min, a_max = bounds.get("area_min", 10.0), bounds.get("area_max", 20000.0)
        if np.any(areas < a_min - 1e-9) or np.any(areas > a_max + 1e-9):
            return {
                "objective": float("inf"),
                "feasible": False,
                "error": f"Area variables out of bounds [{a_min}, {a_max}]",
                "score": float("inf"),
            }
        areas = np.clip(areas, a_min, a_max)

    tp = problem["tower_parameters"]
    nodes, elements = generate_tower_topology(
        num_levels=tp["num_levels"],
        total_height=tp["total_height_mm"],
        bottom_half_width=tp["bottom_half_width_mm"],
        top_half_width=tp["top_half_width_mm"],
        cross_bracing_levels=tp["cross_bracing_levels"],
    )

    n_elements = len(elements)
    if n_elements != problem["num_bars"]:
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": (
                f"Topology mismatch: generated {n_elements} bars, "
                f"expected {problem['num_bars']}"
            ),
            "score": float("inf"),
        }

    E = problem["material"]["E"]
    rho = problem["material"]["rho"]
    supports = problem["supports"]
    fem = TrussFEM3D(nodes, elements, E, supports)

    constraints = problem["constraints"]
    sigma_limit = constraints["stress_limit"]
    disp_limit = constraints["displacement_limit"]
    tol = constraints.get("tolerance", 1e-6)

    supported_nodes = {s["node"] for s in problem["supports"]}
    unsupported_nodes = [i for i in range(problem["num_nodes"]) if i not in supported_nodes]
    num_unsupported = len(unsupported_nodes)

    max_stress_vio = 0.0
    max_disp_vio = 0.0

    for lc in problem["load_cases"]:
        force_vec = np.zeros(3 * problem["num_nodes"])

        if len(lc.get("loads", [])) == 0:
            if lc["id"] == 0:
                load_per_node = 12000.0 / num_unsupported
                for nid in unsupported_nodes:
                    force_vec[3 * nid] += load_per_node
            elif lc["id"] == 1:
                load_per_node = 12000.0 / num_unsupported
                for nid in unsupported_nodes:
                    force_vec[3 * nid + 1] += load_per_node
            elif lc["id"] == 2:
                load_per_node = 15000.0 / num_unsupported
                for nid in unsupported_nodes:
                    force_vec[3 * nid + 2] -= load_per_node
        else:
            for load in lc["loads"]:
                nid = load["node"]
                force_vec[3 * nid] += load["fx"]
                force_vec[3 * nid + 1] += load["fy"]
                force_vec[3 * nid + 2] += load["fz"]

        displacements, stresses = fem.solve(areas, force_vec)
        abs_stresses = np.abs(stresses)
        stress_violations = abs_stresses - sigma_limit
        lc_max_stress_vio = float(np.max(stress_violations))
        max_stress_vio = max(max_stress_vio, lc_max_stress_vio)

        abs_disp = np.abs(displacements)
        disp_violations = abs_disp - disp_limit
        lc_max_disp_vio = float(np.max(disp_violations))
        max_disp_vio = max(max_disp_vio, lc_max_disp_vio)

    weight = fem.compute_weight(areas, rho)
    # Hard gate, never a penalty multiplier.
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
    refs = _references_dir(repo_root)
    if refs is not None:
        for name in ("problem_data.json", "section_database.json"):
            src = refs / name
            if src.is_file():
                inputs[f"references/{name}"] = src
    # Empty placeholders at both accepted submission paths. `expected_outputs`
    # treats a missing file as a hard error and we accept either location; a
    # placeholder the candidate never wrote stays zero bytes and reads back as
    # "not produced".
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


def evaluate(program_path: str, *, repo_root: Path | None = None, algorithm_config: dict | None = None) -> Any:
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

    # Problem data is loaded *before* the candidate runs and never re-read
    # afterwards, so nothing the candidate writes can influence the instance
    # it is scored against.
    problem = load_problem_data(repo_root)
    if problem is None:
        metrics["runtime_s"] = float(time.time() - start)
        artifacts["error_message"] = "problem_data.json not found"
        return _wrap(metrics, artifacts)

    timeout = _CANDIDATE_TIMEOUT_S
    if algorithm_config and "timeout" in algorithm_config:
        timeout = float(algorithm_config["timeout"])

    try:
        run = sandbox.run_candidate_isolated(
            program_path_resolved,
            inputs=_stage_inputs(repo_root),
            expected_outputs=_SUBMISSION_RELPATHS,
            timeout_s=timeout,
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

    # Invariant 3: a crash or a timeout is a failure, full stop. Note that we
    # gate on the return code ONLY -- the previous version also failed the run
    # whenever the candidate wrote anything at all to stderr, which killed
    # honest submissions over a numpy RuntimeWarning.
    if run.timed_out:
        metrics["timeout"] = 1.0
        metrics["runtime_s"] = float(time.time() - start)
        artifacts["error_message"] = f"program timeout after {timeout}s"
        return _wrap(metrics, artifacts)

    if run.returncode != 0:
        metrics["runtime_s"] = float(time.time() - start)
        artifacts["error_message"] = (
            f"program exited non-zero (returncode={run.returncode}); "
            "a surviving submission.json does not excuse a crash"
        )
        return _wrap(metrics, artifacts)

    raw, rel = _pick_submission_bytes(run)
    if raw is None:
        metrics["runtime_s"] = float(time.time() - start)
        artifacts["error_message"] = "submission.json not found"
        return _wrap(metrics, artifacts)
    artifacts["submission_path"] = rel

    try:
        submission = json.loads(raw.decode("utf-8"))
        artifacts["submission.json"] = json.dumps(submission, indent=2)
    except Exception as exc:
        metrics["runtime_s"] = float(time.time() - start)
        artifacts["error_message"] = f"Failed to parse submission.json: {exc}"
        return _wrap(metrics, artifacts)

    solution_vector, reason = validate_submission(submission, problem)
    if solution_vector is None:
        metrics["runtime_s"] = float(time.time() - start)
        artifacts["error_message"] = reason
        return _wrap(metrics, artifacts)

    if isinstance(submission, dict):
        ignored = sorted(
            k for k in submission if k not in ("solution_vector", "num_evaluations")
        )
        if ignored:
            artifacts["ignored_submission_fields"] = ", ".join(ignored)

    # Self-reported budget gate. Kept, but never presented as verified.
    max_eval = problem.get("optimization", {}).get("max_evaluations", None)
    num_eval = submission.get("num_evaluations", 0)
    artifacts["num_evaluations_reported"] = str(num_eval)
    artifacts["num_evaluations_status"] = "unverified"
    artifacts["num_evaluations_note"] = _MAX_EVAL_NOTE
    metrics["num_evaluations_verified"] = 0.0
    if max_eval is not None and isinstance(num_eval, (int, float)) and not isinstance(num_eval, bool) and num_eval > max_eval:
        metrics["runtime_s"] = float(time.time() - start)
        artifacts["error_message"] = f"Exceeded max evaluations: {num_eval} > {max_eval}"
        return _wrap(metrics, artifacts)

    result = build_fem_and_evaluate(solution_vector, problem, repo_root)
    artifacts["evaluation_result"] = json.dumps(result, indent=2)

    runtime_s = time.time() - start
    objective = result.get("objective", 0.0)
    feasible = result.get("feasible", False)

    metrics["weight_kg"] = objective
    metrics["runtime_s"] = float(runtime_s)
    metrics["feasible"] = 1.0 if feasible else 0.0
    metrics["max_stress_violation"] = result.get("max_stress_violation", 0.0)
    metrics["max_displacement_violation"] = result.get(
        "max_displacement_violation", 0.0
    )

    if feasible and np.isfinite(objective) and objective > 0:
        metrics["combined_score"] = -float(objective)
        metrics["valid"] = 1.0
    else:
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
    if len(sys.argv) < 2:
        print("Usage: python evaluator.py <program_path>")
        print("  or:  python evaluator.py --test <submission.json>")
        sys.exit(1)

    if sys.argv[1] == "--test" and len(sys.argv) >= 3:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            sub = json.load(f)
        repo = _find_repo_root()
        prob = load_problem_data(repo)
        result = build_fem_and_evaluate(sub["solution_vector"], prob, repo)
        print(json.dumps(result, indent=2))
    else:
        result = evaluate(sys.argv[1])
        if hasattr(result, "metrics"):
            output = {"metrics": result.metrics, "artifacts": result.artifacts}
        else:
            output = result
        print(json.dumps(output, indent=2))
