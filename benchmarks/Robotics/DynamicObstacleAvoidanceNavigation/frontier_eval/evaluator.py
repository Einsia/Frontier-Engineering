"""Hardened unified evaluator for Robotics/DynamicObstacleAvoidanceNavigation.

What was wrong
--------------
The previous version copied the whole benchmark tree into a scratch directory,
ran the candidate inside it, and *then* did::

    eval_path = sandbox_task / "verification" / "evaluator.py"
    spec.loader.exec_module(module)
    result = module.evaluate(sandbox_submission)

Two separate holes followed from that ordering, both confirmed by running
attack candidates against the old file:

1. **The scorer was loaded from a directory the candidate had just written to.**
   A candidate whose ``main()`` overwrote ``../verification/evaluator.py`` with
   ``def evaluate(*a, **k): return {"score": 0.0, "feasible": True}`` was scored
   by its own code. Measured ``combined_score`` went from 0.0722 (honest
   baseline, 12.85 s mean arrival) to 1.0 -- the maximum the metric can take,
   since ``combined_score = 1 / (1 + arrival_time)``.
2. **The environment being scored came from the same writable copy.** The
   verification module resolves ``references/scenarios.json`` relative to its own
   ``__file__``, so rewriting the sandbox copy replaced the scenes the
   *submission was graded against*. A candidate that deleted every obstacle and
   moved each goal onto its own start scored 1.0 with an all-zero control
   sequence -- the same "candidate supplies the instance" defect found in
   JobShop.

The fix
-------
* ``benchmarks/_shared/candidate_sandbox`` runs the candidate as a subprocess.
  It never enters this process, so it cannot rebind a scoring function.
* The trusted scenario bytes are read, and the trusted scoring module is
  imported (numpy included), **before** the candidate is started, from the
  pristine benchmark directory rather than from anything the candidate can
  reach. That is invariant 1 of the sandbox helper's docstring.
* The candidate is staged into a minimal tree containing only its own file and a
  private copy of ``references/scenarios.json``. Whatever it does to that copy is
  irrelevant: scoring uses the bytes captured beforehand.
* The candidate returns a *trajectory* (``timestamps`` / ``controls``) and
  nothing else. Collision checking, bounds, the kinematic limits, goal arrival
  and the arrival time are all recomputed here from the trusted scenes. No field
  the candidate reports is read; there is no self-reported ``time`` /
  ``collisions`` / ``success`` path into the metrics.

Deliberately unchanged: the unicycle integration, the goal tolerance, the
arrival-time objective and the all-scenes-must-succeed hard gate all still live
in ``verification/evaluator.py``. An honest candidate's score is bit-identical to
the pre-hardening value.
"""


from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType
from typing import Any

# The pre-hardening evaluator reported 0.0 for an unusable run. 0.0 is the
# infimum of this task's metric (``1/(1+t)`` is strictly positive for every
# finite arrival time), so it already dominates nothing; it is kept verbatim
# so hardening moves no published number, honest or otherwise.
INVALID_COMBINED_SCORE = 0.0

TASK_NAME = "DynamicObstacleAvoidanceNavigation"
CONTROL_DIM = 2  # (v, omega)

# Scorer-owned sanity caps on the returned trajectory. The trusted simulator is
# strict about physics but happily allocates whatever array it is handed, and it
# compares NaN against the limits (every ``NaN > v_max`` is False), so the
# structural gate belongs here, ahead of it.
MAX_SCENARIO_ENTRIES = 64
MAX_SAMPLES_PER_SCENARIO = 200_000
MAX_SUBMISSION_BYTES = 32 * 1024 * 1024

# Keep FRONTIER_ENGINEERING_ROOT and the harness variables away from the child so
# it is not simply handed the path of the tree it must not touch. This raises the
# cost of finding the real repo; it does not close /proc/<ppid>/ (see the helper
# docstring). HOME is required: numpy may live in the per-user site directory.
CANDIDATE_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LD_LIBRARY_PATH",
    "TMPDIR",
    "TERM",
)

# FSIZE bounds a candidate that tries to fill the disk (or hand us a submission
# too large to parse); NOFILE bounds descriptor exhaustion. No RLIMIT_AS: BLAS
# reserves large virtual arenas and would fail to initialise.
CANDIDATE_RLIMITS = {"FSIZE": 64 * 1024 * 1024, "NOFILE": 1024}


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)


def _repo_root_guess(repo_root: Path | None) -> Path:
    if repo_root is not None:
        return Path(repo_root).expanduser().resolve()
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    return Path.cwd().resolve()


def _resolve_benchmark_dir(repo_root: Path) -> Path:
    candidates = (
        repo_root / "benchmarks" / "Robotics" / TASK_NAME,
        repo_root / "Robotics" / TASK_NAME,
    )
    for cand in candidates:
        if cand.is_dir():
            return cand.resolve()
    # Last resort: the copy this file lives in. Only reached when the harness did
    # not hand us a repo root; it is still a directory the candidate has not run
    # in yet, because everything trusted is read before the candidate starts.
    return Path(__file__).resolve().parents[1]


def _import_sandbox_helper(repo_root: Path) -> ModuleType:
    shared = repo_root / "benchmarks" / "_shared"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import candidate_sandbox  # noqa: PLC0415

    return candidate_sandbox


def _load_trusted_scorer(evaluator_path: Path) -> ModuleType:
    """exec_module the *pristine* verification module, before the candidate runs.

    This is a scorer-owned file, never a candidate-owned one; the whole point of
    the ordering is that nothing the candidate does can change what lands here.
    """
    spec = importlib.util.spec_from_file_location("fe_dynamic_obstacle_navigation_trusted_eval", evaluator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load trusted evaluator: {evaluator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "evaluate"):
        raise RuntimeError(f"trusted evaluator defines no evaluate(): {evaluator_path}")
    return module


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _validate_submission(obj: Any, expected_ids: list[str]) -> tuple[dict[str, Any] | None, str]:
    """Scorer-side structural gate on the candidate's trajectory.

    Returns a *rebuilt* submission containing only the three fields the simulator
    consumes, so nothing else a candidate puts in the file can reach the scorer.
    """
    if not isinstance(obj, dict):
        return None, "submission must be a JSON object"
    entries = obj.get("scenarios")
    if not isinstance(entries, list):
        return None, "submission['scenarios'] must be a list"
    if len(entries) > MAX_SCENARIO_ENTRIES:
        return None, f"too many scenario entries: {len(entries)} > {MAX_SCENARIO_ENTRIES}"

    allowed = set(expected_ids)
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return None, f"scenarios[{i}] must be an object"
        sid = entry.get("id")
        if not isinstance(sid, str):
            return None, f"scenarios[{i}]['id'] must be a string"
        if sid not in allowed:
            return None, f"scenarios[{i}]['id']={sid!r} is not a known scene"
        if sid in seen:
            return None, f"duplicate entry for scene {sid!r}"
        seen.add(sid)

        timestamps = entry.get("timestamps")
        controls = entry.get("controls")
        if not isinstance(timestamps, list) or not isinstance(controls, list):
            return None, f"{sid}: timestamps and controls must be lists"
        if len(timestamps) > MAX_SAMPLES_PER_SCENARIO:
            return None, f"{sid}: {len(timestamps)} samples exceeds {MAX_SAMPLES_PER_SCENARIO}"
        if len(timestamps) != len(controls):
            return None, f"{sid}: len(timestamps) != len(controls)"
        if not all(_finite_number(t) for t in timestamps):
            return None, f"{sid}: timestamps must be finite numbers"
        for k, u in enumerate(controls):
            if not isinstance(u, list) or len(u) != CONTROL_DIM:
                return None, f"{sid}: controls[{k}] must be a list of {CONTROL_DIM} numbers"
            if not all(_finite_number(c) for c in u):
                return None, f"{sid}: controls[{k}] must be finite"

        clean.append(
            {
                "id": sid,
                "timestamps": [float(t) for t in timestamps],
                "controls": [[float(c) for c in u] for u in controls],
            }
        )

    return {"scenarios": clean}, "ok"


def evaluate(program_path: str, *, repo_root: Path | None = None):
    start = time.time()
    program_path_p = Path(program_path).expanduser().resolve()
    root = _repo_root_guess(repo_root)
    benchmark_dir = _resolve_benchmark_dir(root)

    metrics: dict[str, float] = {
        "combined_score": INVALID_COMBINED_SCORE,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }
    artifacts: dict[str, str] = {}

    def _bail(message: str):
        artifacts["error_message"] = message
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    if not benchmark_dir.is_dir():
        return _bail(f"benchmark dir not found: {benchmark_dir}")
    if not program_path_p.is_file():
        return _bail(f"program not found: {program_path_p}")

    # ---------------------------------------------------------------- trusted
    # Everything below happens before the candidate is started (invariant 1).
    scenarios_src = benchmark_dir / "references" / "scenarios.json"
    trusted_eval_src = benchmark_dir / "verification" / "evaluator.py"
    if not scenarios_src.is_file():
        return _bail(f"scenarios not found: {scenarios_src}")
    if not trusted_eval_src.is_file():
        return _bail(f"trusted evaluator not found: {trusted_eval_src}")

    scenarios_bytes = scenarios_src.read_bytes()
    trusted_eval_bytes = trusted_eval_src.read_bytes()
    artifacts["trusted_scenarios_sha256"] = _sha256(scenarios_bytes)
    artifacts["trusted_evaluator_sha256"] = _sha256(trusted_eval_bytes)

    try:
        cfg = json.loads(scenarios_bytes.decode("utf-8-sig"))
        expected_ids = [str(scene["id"]) for scene in cfg["scenarios"]]
    except Exception as exc:
        return _bail(f"trusted scenarios unreadable: {exc}")

    try:
        sandbox = _import_sandbox_helper(root)
        trusted = _load_trusted_scorer(trusted_eval_src)
    except Exception as exc:
        return _bail(f"failed to prepare trusted scoring context: {exc}")

    # -------------------------------------------------------------- candidate
    timeout_s = float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "240") or "240")
    timeout_s = max(1.0, timeout_s)

    # The published contract is `Path(__file__).parents[1] / "references" /
    # "scenarios.json"`, so the candidate needs a two-level tree. It gets a
    # minimal one holding only itself and its own copy of the scenes -- no
    # verification code, no reference material, nothing worth tampering with.
    stage = Path(tempfile.mkdtemp(prefix="fe_dynnav_stage_")).resolve()
    private = Path(tempfile.mkdtemp(prefix="fe_dynnav_score_")).resolve()
    try:
        (stage / "baseline").mkdir(parents=True)
        (stage / "references").mkdir(parents=True)
        (stage / "references" / "scenarios.json").write_bytes(scenarios_bytes)
        staged_program = stage / "baseline" / "solution.py"
        shutil.copy2(program_path_p, staged_program)

        try:
            run = sandbox.run_candidate_isolated(
                staged_program,
                # Seeded so a candidate that never writes still produces the
                # expected output and we keep its return code (invariant 3)
                # instead of losing it to a missing-output exception.
                inputs={"submission.json": b""},
                expected_outputs=("submission.json",),
                timeout_s=timeout_s,
                # Run in place: the contract above needs __file__ inside `stage`.
                # `stage` is ours and contains nothing sensitive.
                copy_into_workdir=False,
                env_allowlist=CANDIDATE_ENV_ALLOWLIST,
                rlimits=CANDIDATE_RLIMITS,
            )
        except sandbox.InvalidSubmissionError as exc:
            return _bail(f"candidate produced no usable output: {exc}")

        artifacts["candidate_stdout"] = run.stdout_tail
        artifacts["candidate_stderr"] = run.stderr_tail
        metrics["candidate_returncode"] = float(run.returncode)
        if run.timed_out:
            metrics["timeout"] = 1.0
            return _bail("candidate timeout")
        if run.returncode != 0:
            return _bail("candidate program exited non-zero")

        submission_bytes = run.read_output_bytes("submission.json")
        if not submission_bytes.strip():
            # Some candidates write next to __file__ rather than into cwd; both
            # locations are candidate-owned data and validated identically.
            alt = stage / "baseline" / "submission.json"
            if alt.is_file():
                submission_bytes = alt.read_bytes()
        if not submission_bytes.strip():
            return _bail("candidate did not generate submission.json")
        if len(submission_bytes) > MAX_SUBMISSION_BYTES:
            return _bail(f"submission.json too large: {len(submission_bytes)} bytes")

        try:
            raw = json.loads(submission_bytes.decode("utf-8-sig"))
        except Exception as exc:
            return _bail(f"invalid submission json: {exc}")

        clean, reason = _validate_submission(raw, expected_ids)
        if clean is None:
            return _bail(f"invalid submission: {reason}")

        # ------------------------------------------------------------- score
        # Trusted scenes + rebuilt trajectory, both written to a directory the
        # candidate was never told about, scored by the module imported above.
        scoring_scenarios = private / "scenarios.json"
        scoring_submission = private / "submission.json"
        scoring_scenarios.write_bytes(scenarios_bytes)
        scoring_submission.write_text(json.dumps(clean), encoding="utf-8")

        result: dict[str, Any] = trusted.evaluate(scoring_submission, scoring_scenarios)
        artifacts["evaluation_result"] = json.dumps(result, ensure_ascii=False)

        feasible = bool(result.get("feasible", False))
        metrics["feasible"] = 1.0 if feasible else 0.0
        if not feasible:
            return _bail("infeasible navigation trajectory")

        raw_score = result.get("score")
        if not _finite_number(raw_score):
            return _bail(f"trusted scorer returned a non-finite score: {raw_score!r}")

        arrival_time = float(raw_score)
        if arrival_time < 0.0:
            return _bail(f"trusted scorer returned a negative arrival time: {arrival_time}")

        metrics["valid"] = 1.0
        metrics["arrival_time_s"] = arrival_time
        metrics["combined_score"] = float(1.0 / (1.0 + arrival_time))
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(private, ignore_errors=True)
