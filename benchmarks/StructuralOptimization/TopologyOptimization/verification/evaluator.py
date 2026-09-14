"""Evaluator for TopologyOptimization.

The candidate returns the flattened nelx*nely density field. The scorer computes
FEM response, compliance, volume constraint and score from those design variables.
Scoring dependencies are imported before candidate execution. Timeouts and
nonzero exits are rejected even when a submission file exists.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

INVALID_COMBINED_SCORE = -1e18

_HERE = Path(__file__).resolve().parent
_BENCHMARK_DIR = _HERE.parent

try:  # optional: only present when running under openevolve
    from openevolve.evaluation_result import EvaluationResult as _EvaluationResult
except Exception:  # pragma: no cover - depends on the deployment env
    _EvaluationResult = None


def _locate_shared_dir() -> Path:
    """Find ``benchmarks/_shared``, which lives outside every benchmark tree.

    ``copy_files.txt`` is ``.`` here, so the sandbox holds a writable copy of
    the whole benchmark directory. The isolation helper is deliberately kept
    outside it: a candidate can never rewrite the code that runs it.
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


def _find_repo_root(start: Path | None = None) -> Path:
    """Locate the repository root directory."""
    if "FRONTIER_ENGINEERING_ROOT" in os.environ:
        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "frontier_eval").is_dir() and (parent / "benchmarks").is_dir():
            return parent
    return Path.cwd().resolve()


def _tail(text: str, limit: int = 8000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _truncate_middle(text: str, limit: int = 200_000) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, (limit - 128) // 2)
    omitted = len(text) - 2 * keep
    return text[:keep] + f"\n\n[... truncated {omitted} chars ...]\n\n" + text[-keep:]


def _references_dir(repo_root: Path) -> Path | None:
    for refs in (
        repo_root / "benchmarks" / "StructuralOptimization" / "TopologyOptimization"
        / "references",
        repo_root / "StructuralOptimization" / "TopologyOptimization" / "references",
        _BENCHMARK_DIR / "references",
    ):
        if (refs / "problem_config.json").is_file():
            return refs
    return None


def load_problem_config(repo_root: Path) -> dict:
    """Load the problem configuration JSON.

    ``repo_root`` is the *real* repository root (the harness exports
    ``FRONTIER_ENGINEERING_ROOT``), not the sandbox copy, so the mesh, the
    volume fraction, the penalisation and the load used for scoring are the
    pristine ones even if the sandbox copy is tampered with.
    """
    candidates = [
        repo_root / "benchmarks" / "StructuralOptimization" / "TopologyOptimization"
        / "references" / "problem_config.json",
        repo_root / "StructuralOptimization" / "TopologyOptimization"
        / "references" / "problem_config.json",
        _BENCHMARK_DIR / "references" / "problem_config.json",
    ]
    for path in candidates:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(
        f"problem_config.json not found. Searched: {[str(p) for p in candidates]}"
    )


# ============================================================================
# Independent FEM solver (mirrors init.py exactly)
# ============================================================================

def _element_stiffness_matrix(nu: float) -> np.ndarray:
    """8x8 element stiffness matrix for unit-size Q4 element, plane stress."""
    k = np.array([
        1/2 - nu/6, 1/8 + nu/8, -1/4 - nu/12, -1/8 + 3*nu/8,
        -1/4 + nu/12, -1/8 - nu/8, nu/6, 1/8 - 3*nu/8
    ])
    KE = (1.0 / (1.0 - nu**2)) * np.array([
        [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
        [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
        [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
        [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
        [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
        [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
        [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
        [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
    ])
    return KE


def _fem_solve(nelx: int, nely: int, density: np.ndarray, config: dict) -> np.ndarray:
    """Solve the 2D FEM problem with Q4 elements. Returns displacement vector."""
    E0 = config["E0"]
    Emin = config["Emin"]
    nu = config["nu"]
    penal = config["penal"]

    KE = _element_stiffness_matrix(nu)
    n_dofs = 2 * (nelx + 1) * (nely + 1)

    iK = np.zeros(64 * nelx * nely, dtype=int)
    jK = np.zeros(64 * nelx * nely, dtype=int)
    sK = np.zeros(64 * nelx * nely, dtype=float)

    for elx in range(nelx):
        for ely in range(nely):
            e_idx = elx * nely + ely
            n1 = elx * (nely + 1) + ely
            n2 = (elx + 1) * (nely + 1) + ely
            edof = np.array([
                2*n1, 2*n1+1,
                2*n2, 2*n2+1,
                2*n2+2, 2*n2+3,
                2*n1+2, 2*n1+3,
            ])
            Ee = Emin + density[ely, elx]**penal * (E0 - Emin)
            for i_local in range(8):
                for j_local in range(8):
                    idx = e_idx * 64 + i_local * 8 + j_local
                    iK[idx] = edof[i_local]
                    jK[idx] = edof[j_local]
                    sK[idx] = Ee * KE[i_local, j_local]

    K = coo_matrix((sK, (iK, jK)), shape=(n_dofs, n_dofs)).tocsc()

    F = np.zeros(n_dofs)
    F[1] = config["force"]["fy"]

    fixed_dofs = []
    for i in range(nely + 1):
        fixed_dofs.append(2 * i)
    fixed_dofs.append(2 * (nelx * (nely + 1) + nely) + 1)

    fixed_dofs = np.array(fixed_dofs, dtype=int)
    all_dofs = np.arange(n_dofs)
    free_dofs = np.setdiff1d(all_dofs, fixed_dofs)

    K_ff = K[free_dofs, :][:, free_dofs]
    F_f = F[free_dofs]

    u = np.zeros(n_dofs)
    u[free_dofs] = spsolve(K_ff, F_f)

    return u


def _compute_compliance(
    nelx: int, nely: int, density: np.ndarray, u: np.ndarray, config: dict
) -> float:
    """Compute total compliance c = F^T u via element summation."""
    E0 = config["E0"]
    Emin = config["Emin"]
    nu = config["nu"]
    penal = config["penal"]

    KE = _element_stiffness_matrix(nu)

    compliance = 0.0
    for elx in range(nelx):
        for ely in range(nely):
            n1 = elx * (nely + 1) + ely
            n2 = (elx + 1) * (nely + 1) + ely
            edof = np.array([
                2*n1, 2*n1+1,
                2*n2, 2*n2+1,
                2*n2+2, 2*n2+3,
                2*n1+2, 2*n1+3,
            ])
            ue = u[edof]
            Ee = Emin + density[ely, elx]**penal * (E0 - Emin)
            compliance += Ee * float(ue @ KE @ ue)

    return compliance


def evaluate_topology(
    density_vector: list[float], config: dict
) -> dict[str, Any]:
    """
    Evaluate a topology optimization solution.

    Parameters
    ----------
    density_vector : list of float
        Flattened density field of length nelx * nely.
    config : dict
        Problem configuration.

    Returns
    -------
    result : dict
        Evaluation results including compliance, volume fraction, feasibility.
    """
    nelx = config["nelx"]
    nely = config["nely"]
    volfrac = config["volfrac"]
    rho_min = 1e-3

    expected_len = nelx * nely
    x = np.array(density_vector, dtype=float)

    # --- Input validation ---
    if len(x) != expected_len:
        return {
            "compliance": float("inf"),
            "volume_fraction": 0.0,
            "feasible": False,
            "error": f"Expected {expected_len} elements, got {len(x)}",
        }

    if not np.all(np.isfinite(x)):
        return {
            "compliance": float("inf"),
            "volume_fraction": 0.0,
            "feasible": False,
            "error": "Density vector contains NaN or Inf values",
        }

    # Clip densities to valid range
    x = np.clip(x, rho_min, 1.0)
    density = x.reshape((nely, nelx))

    # --- FEM solve ---
    try:
        u = _fem_solve(nelx, nely, density, config)
    except Exception as exc:
        return {
            "compliance": float("inf"),
            "volume_fraction": float(np.mean(density)),
            "feasible": False,
            "error": f"FEM solve failed: {exc}",
        }

    # --- Compute compliance ---
    try:
        compliance = _compute_compliance(nelx, nely, density, u, config)
    except Exception as exc:
        return {
            "compliance": float("inf"),
            "volume_fraction": float(np.mean(density)),
            "feasible": False,
            "error": f"Compliance computation failed: {exc}",
        }

    vol_frac = float(np.mean(density))

    # Volume fraction constraint: Σρ / N ≤ volfrac (with tolerance)
    feasible = vol_frac <= volfrac + 1e-6

    return {
        "compliance": float(compliance),
        "volume_fraction": vol_frac,
        "feasible": bool(feasible),
    }


def validate_submission(submission: Any, config: dict) -> tuple[list[float] | None, str]:
    """Scorer-owned structural check, run before any physics.

    Only ``density_vector`` is consumed; every other key the candidate writes
    (``compliance``, ``volume_fraction``, ``score``, ...) is ignored by
    construction.
    """
    if not isinstance(submission, dict):
        return None, "submission.json must contain a JSON object"
    if "density_vector" not in submission:
        return None, "submission.json missing 'density_vector'"

    raw = submission["density_vector"]
    if not isinstance(raw, list):
        return None, "'density_vector' must be a JSON list"

    expected_len = int(config["nelx"]) * int(config["nely"])
    if len(raw) != expected_len:
        return None, f"Expected {expected_len} elements, got {len(raw)}"

    values: list[float] = []
    for i, item in enumerate(raw):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None, f"'density_vector[{i}]' must be a number, got {type(item).__name__}"
        values.append(float(item))

    return values, ""


def _stage_inputs(repo_root: Path) -> dict[str, Any]:
    """Read-only copies the candidate is allowed to see inside its sandbox."""
    inputs: dict[str, Any] = {}
    refs = _references_dir(repo_root)
    if refs is not None:
        inputs["references/problem_config.json"] = refs / "problem_config.json"
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


def evaluate(program_path: str, *, repo_root: Path | None = None) -> Any:
    """
    Full evaluation pipeline:
    1. Run the candidate in an isolated subprocess; it may only produce data
    2. Validate the submission's shape (scorer-owned, before any physics)
    3. Run this process's own FEM + volume check on the density field
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
        "compliance": 0.0,
        "volume_fraction": 0.0,
        "valid": 0.0,
        "feasible": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }

    # 1. Config is loaded *before* the candidate runs and never re-read
    #    afterwards, so nothing the candidate writes can change the instance
    #    it is scored against.
    config = load_problem_config(repo_root)

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

    # Reject timeouts and nonzero exits even if a result file was written.
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

    density_vector, reason = validate_submission(submission, config)
    if density_vector is None:
        artifacts["error_message"] = reason
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    if isinstance(submission, dict):
        ignored = sorted(k for k in submission if k != "density_vector")
        if ignored:
            artifacts["ignored_submission_fields"] = ", ".join(ignored)

    # 4. Score, recomputed here from the density field alone.
    result = evaluate_topology(density_vector, config)
    artifacts["evaluation_result"] = json.dumps(result, indent=2)

    runtime_s = time.time() - start
    metrics["compliance"] = result.get("compliance", 0.0)
    metrics["volume_fraction"] = result.get("volume_fraction", 0.0)
    metrics["runtime_s"] = float(runtime_s)
    metrics["feasible"] = 1.0 if result.get("feasible", False) else 0.0

    if result.get("feasible", False):
        # Minimization: negate compliance so higher combined_score = better
        metrics["combined_score"] = -float(result["compliance"])
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
        sys.exit(1)

    result = evaluate(sys.argv[1])
    if hasattr(result, "metrics"):
        output = {"metrics": result.metrics, "artifacts": result.artifacts}
    else:
        output = result
    print(json.dumps(output, indent=2))
