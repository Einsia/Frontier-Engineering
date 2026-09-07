"""Hardened unified evaluator for Robotics/RobotArmCycleTimeOptimization.

What was wrong
--------------
The candidate was already run as a subprocess, but the scoring code was fetched
*after* it had had a turn on the same filesystem::

    proc = subprocess.run([sys.executable, sandbox_program], ...)   # candidate
    ...
    eval_path = (benchmark_dir / "verification" / "evaluator.py").resolve()
    spec.loader.exec_module(module)                                 # scorer
    raw_score = float(module.evaluate(sandbox_submission))

``benchmark_dir`` comes from ``FRONTIER_ENGINEERING_ROOT``, which the harness
points at the real repository, and the whole environment was passed straight
through to the child. That is invariant 1 of ``benchmarks/_shared/candidate_sandbox``
violated, and it was confirmed exploitable against the old file:

1. **Scorer loaded from a path the candidate had just written.** A candidate
   whose body was ``(repo/.../verification/evaluator.py).write_text(
   "def evaluate(p): return 0.0")`` plus a junk ``{"junk": 1}`` submission was
   graded by its own code: ``combined_score`` 0.2921925682511491 (honest
   baseline, 2.4224 s cycle time) -> **1.0**, the supremum of ``1/(1+T)``.
2. **The robot and the world came from a writable path too.** The trusted
   evaluator loads ``plane.urdf`` and ``kuka_iiwa/model.urdf`` through
   ``pybullet_data.getDataPath()``, which resolves into the user's writable
   site-packages directory -- outside the repository, so the harness' source-tree
   fingerprint does not cover it. Measured against the old file (with the data
   path redirected to a scratch copy, so the real site-packages was never
   touched): a candidate that submitted the honest baseline trajectory and also
   inverted every ``<limit lower=... upper=...>`` in ``kuka_iiwa/model.urdf`` was
   graded on its own robot -- ``combined_score`` 0.2921925682511491 -> **0.0**,
   because the evaluator then bailed with "invalid joint limits from URDF".
   That direction is score *suppression*; no score-inflating exploit was found
   through this path, because neither the URDF joint limits nor the obstacle
   binds the optimum here (see the sampling note below). It is closed anyway: a
   candidate that can rewrite the model can decide what any *later* candidate is
   graded on.

A third defect is in the trusted evaluator itself and is fixed there:
``_validate_format`` gated everything with ``>``/``<``, and every comparison
against NaN is False, so all-NaN ``waypoints`` passed the start/goal tolerance,
the joint limits, the velocity and acceleration limits and the collision query.
Only ``scipy.interpolate.CubicSpline``'s internal "`y` must contain only finite
values" assertion stopped it -- see the note at the bottom of this docstring.

The fix
-------
* A *private* copy of ``verification/`` and ``references/`` is staged, and the
  trusted scorer is exec_module'd from that copy, **before** the candidate is
  started. The candidate is never told where it is, and scoring never reads the
  repository again.
* The pybullet asset subset the trusted evaluator loads (``plane.*``,
  ``kuka_iiwa/``) is copied out of ``pybullet_data`` into the same private tree
  before the candidate runs, and the trusted module's ``pybullet_data`` global is
  rebound to a shim returning that private path. Rewriting site-packages after
  the fact no longer changes the robot being scored.
* The candidate runs via ``candidate_sandbox.run_candidate_isolated``: its own
  process, a scrubbed environment (no ``FRONTIER_ENGINEERING_ROOT``), resource
  limits and a hard timeout. It never enters this process.
* The submission is re-validated here and *rebuilt* into exactly
  ``{"waypoints", "timestamps"}`` of finite floats, so no other field and no
  non-finite value can reach the simulator.

Deliberately unchanged: the cubic-spline interpolation, the 30-samples-per-segment
sweep, the joint/velocity/acceleration limits, the PyBullet contact query and the
``score = timestamps[-1]`` objective all still live in
``verification/evaluator.py`` and are still the only thing that produces a number.
An honest candidate's score is bit-identical to the pre-hardening value
(cycle_time_s 2.4224005284777377, combined_score 0.2921925682511491 for
``baseline/solution.py``).

Not fixed here, reported instead: each segment is sampled at 30 points with
``endpoint=False``, so the final timestamp -- and therefore the goal
configuration -- is never collision-checked, and a violation can hide between
samples. Tightening that moves honest scores, so it is a product decision.
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

# The pre-hardening evaluator reported 0.0 for an unusable run. ``1/(1+T)`` is
# strictly positive for every admissible T (timestamps[0] == 0 and strictly
# increasing forces T > 0), so 0.0 already ranks below every valid score; it is
# kept verbatim so hardening moves no published number, honest or otherwise.
INVALID_COMBINED_SCORE = 0.0

TASK_NAME = "RobotArmCycleTimeOptimization"
JOINT_DIM = 7

# Scorer-owned sanity caps. The trusted simulator is strict about physics but
# happily allocates whatever array it is handed and runs 30 collision queries per
# segment, so the structural gate belongs here, ahead of it.
MAX_WAYPOINTS = 1024  # -> at most 30 * 1023 collision queries
MAX_SUBMISSION_BYTES = 32 * 1024 * 1024

# The subset of pybullet_data the trusted evaluator actually loads. Copied into a
# private directory before the candidate runs; anything missing here surfaces as
# a loud loadURDF failure, never as a silently different robot.
PYBULLET_ASSET_DIRS = ("kuka_iiwa",)
PYBULLET_ASSET_FILES = (
    "plane.urdf",
    "plane100.obj",
    "plane.mtl",
    "checker_blue.png",
    "cube.tga",
)

# Keep FRONTIER_ENGINEERING_ROOT and the harness variables away from the child so
# it is not simply handed the path of the tree it must not touch. This raises the
# cost of finding the real repo; it does not close /proc/<ppid>/ (see the helper
# docstring). HOME is required: numpy/pybullet may live in the per-user site
# directory.
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


class _PinnedPybulletData:
    """Stand-in for the ``pybullet_data`` module with a frozen data path."""

    def __init__(self, path: Path) -> None:
        self._path = str(path)

    def getDataPath(self) -> str:  # noqa: N802 - mirrors pybullet_data's API
        return self._path


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
    for cand in (repo_root / "benchmarks" / "Robotics" / TASK_NAME,
                 repo_root / "Robotics" / TASK_NAME):
        if cand.is_dir():
            return cand.resolve()
    # Last resort: the copy this file lives in. Still safe, because everything
    # trusted is read before the candidate has run.
    return Path(__file__).resolve().parents[1]


def _import_sandbox_helper(repo_root: Path) -> ModuleType:
    shared = repo_root / "benchmarks" / "_shared"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import candidate_sandbox  # noqa: PLC0415

    return candidate_sandbox


def _load_trusted_scorer(evaluator_path: Path) -> ModuleType:
    """exec_module the *private* copy of the verification module.

    Called before the candidate is started, from a directory the candidate is
    never told about, so nothing it does can change what lands here.
    """
    spec = importlib.util.spec_from_file_location("fe_robot_arm_trusted_eval", evaluator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load trusted evaluator: {evaluator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "evaluate"):
        raise RuntimeError(f"trusted evaluator defines no evaluate(): {evaluator_path}")
    return module


def _stage_pybullet_assets(dest: Path) -> str:
    """Copy the URDFs and meshes the trusted evaluator loads into ``dest``."""
    import pybullet_data  # noqa: PLC0415

    src = Path(pybullet_data.getDataPath()).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for name in PYBULLET_ASSET_DIRS:
        if (src / name).is_dir():
            shutil.copytree(src / name, dest / name)
    for name in PYBULLET_ASSET_FILES:
        if (src / name).is_file():
            shutil.copy2(src / name, dest / name)
    return str(src)


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _validate_submission(obj: Any) -> tuple[dict[str, Any] | None, str]:
    """Scorer-side structural gate on the candidate's trajectory.

    Returns a *rebuilt* submission holding only the two fields the simulator
    consumes, all finite, so nothing else in the file can reach the scorer. The
    semantic gates (timestamps[0] == 0, strict monotonicity, start/goal
    tolerance, joint/velocity/acceleration limits, collision) stay in the trusted
    evaluator; this only guarantees it is handed well-formed finite numbers.
    """
    if not isinstance(obj, dict):
        return None, "submission must be a JSON object"

    waypoints = obj.get("waypoints")
    timestamps = obj.get("timestamps")
    if not isinstance(waypoints, list) or not isinstance(timestamps, list):
        return None, "'waypoints' and 'timestamps' must both be lists"
    if len(waypoints) < 2:
        return None, f"need at least 2 waypoints, got {len(waypoints)}"
    if len(waypoints) > MAX_WAYPOINTS:
        return None, f"too many waypoints: {len(waypoints)} > {MAX_WAYPOINTS}"
    if len(timestamps) != len(waypoints):
        return None, "'timestamps' and 'waypoints' length mismatch"

    if not all(_finite_number(t) for t in timestamps):
        return None, "'timestamps' must be finite numbers"

    clean_wp: list[list[float]] = []
    for i, row in enumerate(waypoints):
        if not isinstance(row, list) or len(row) != JOINT_DIM:
            return None, f"waypoints[{i}] must be a list of {JOINT_DIM} numbers"
        if not all(_finite_number(q) for q in row):
            return None, f"waypoints[{i}] must be finite"
        clean_wp.append([float(q) for q in row])

    return {"waypoints": clean_wp, "timestamps": [float(t) for t in timestamps]}, "ok"


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

    trusted_eval_src = benchmark_dir / "verification" / "evaluator.py"
    references_src = benchmark_dir / "references"
    if not trusted_eval_src.is_file():
        return _bail(f"trusted evaluator not found: {trusted_eval_src}")

    private = Path(tempfile.mkdtemp(prefix="fe_robotarm_trusted_")).resolve()
    try:
        # ------------------------------------------------------------ trusted
        # Everything in this block happens before the candidate is started.
        trusted_eval_bytes = trusted_eval_src.read_bytes()
        artifacts["trusted_evaluator_sha256"] = hashlib.sha256(trusted_eval_bytes).hexdigest()

        (private / "verification").mkdir(parents=True)
        private_eval = private / "verification" / "evaluator.py"
        private_eval.write_bytes(trusted_eval_bytes)

        # `references/` is not read by the trusted evaluator today, but it is
        # part of the published task tree; staging it keeps the private copy a
        # faithful, self-contained stand-in.
        config_bytes: dict[str, bytes] = {}
        if references_src.is_dir():
            (private / "references").mkdir(parents=True)
            for item in sorted(references_src.iterdir()):
                if item.is_file():
                    data = item.read_bytes()
                    config_bytes[item.name] = data
                    (private / "references" / item.name).write_bytes(data)

        try:
            sandbox = _import_sandbox_helper(root)
            asset_src = _stage_pybullet_assets(private / "pybullet_data")
            trusted = _load_trusted_scorer(private_eval)
            # Pin the world to the private asset copy taken above, so rewriting
            # site-packages after this point cannot change the robot or the floor.
            trusted.pybullet_data = _PinnedPybulletData(private / "pybullet_data")
        except Exception as exc:
            return _bail(f"failed to prepare trusted scoring context: {exc}")
        artifacts["pybullet_data_source"] = asset_src

        # ---------------------------------------------------------- candidate
        timeout_s = max(1.0, float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "240") or "240"))

        inputs: dict[str, bytes | Path] = {
            # Seeded so a candidate that never writes still produces the expected
            # output and we keep its return code (invariant 3) instead of losing
            # it to a missing-output exception.
            "submission.json": b"",
        }
        for name, data in config_bytes.items():
            inputs[f"references/{name}"] = data

        try:
            run = sandbox.run_candidate_isolated(
                program_path_p,
                inputs=inputs,
                expected_outputs=("submission.json",),
                timeout_s=timeout_s,
                # Copy into the sandbox: keeps sys.path[0] and __file__ inside a
                # directory holding nothing but the candidate and its own copy of
                # the references. Matches the pre-hardening contract, where the
                # candidate ran from a scratch dir containing only itself.
                copy_into_workdir=True,
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
            return _bail("candidate did not generate submission.json")
        if len(submission_bytes) > MAX_SUBMISSION_BYTES:
            return _bail(f"submission.json too large: {len(submission_bytes)} bytes")

        try:
            raw = json.loads(submission_bytes.decode("utf-8-sig"))
        except Exception as exc:
            return _bail(f"invalid submission json: {exc}")

        clean, reason = _validate_submission(raw)
        if clean is None:
            return _bail(f"invalid submission: {reason}")

        # -------------------------------------------------------------- score
        scoring_submission = private / "submission.json"
        scoring_submission.write_text(json.dumps(clean), encoding="utf-8")

        try:
            raw_score = float(trusted.evaluate(scoring_submission))
        except Exception as exc:
            return _bail(f"trusted scorer raised: {exc}")

        feasible = math.isfinite(raw_score) and raw_score > 0.0
        metrics["feasible"] = 1.0 if feasible else 0.0
        if not feasible:
            return _bail("infeasible trajectory")

        metrics["valid"] = 1.0
        metrics["cycle_time_s"] = raw_score
        metrics["combined_score"] = float(1.0 / (1.0 + raw_score))
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(private, ignore_errors=True)
