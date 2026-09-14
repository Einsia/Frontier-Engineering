"""Evaluator for quadruped gait optimization.

The scorer snapshots verification code and reference assets before candidate
execution and loads the simulator from that private tree. The candidate runs
in a subprocess and returns eight finite, non-boolean gait parameters within
the trusted bounds. The MuJoCo rollout checks roll, pitch, torque and minimum
progress, then scores distance divided by duration.

The task uses one fixed, unseeded scenario, so it does not measure generalization
to other rollouts. Filesystem visibility depends on the sandbox mode.
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

# Invalid runs receive 0.0, matching hard-constraint failures in the simulator.
INVALID_COMBINED_SCORE = 0.0

TASK_NAME = "QuadrupedGaitOptimization"

PARAM_KEYS = (
    "step_frequency",
    "duty_factor",
    "step_length",
    "step_height",
    "phase_FR",
    "phase_RL",
    "phase_RR",
    "lateral_distance",
)

# Matches the trusted evaluator: the three phase offsets are half-open [lo, hi).
HALF_OPEN_KEYS = frozenset({"phase_FR", "phase_RL", "phase_RR"})

MAX_SUBMISSION_BYTES = 1 * 1024 * 1024

# Keep FRONTIER_ENGINEERING_ROOT and the harness variables away from the child so
# it is not simply handed the path of the tree it must not touch. This raises the
# cost of finding the real repo; it does not close /proc/<ppid>/ (see the helper
# docstring). HOME is required: numpy/mujoco may live in the per-user site
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
    never told about. The module resolves ``references/`` relative to its own
    ``__file__``, so loading it from here also pins the config and the MuJoCo
    model to the private copies staged alongside it.
    """
    spec = importlib.util.spec_from_file_location("fe_quadruped_trusted_eval", evaluator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load trusted evaluator: {evaluator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "evaluate"):
        raise RuntimeError(f"trusted evaluator defines no evaluate(): {evaluator_path}")
    return module


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _validate_params(obj: Any, cfg: dict[str, Any]) -> tuple[dict[str, float] | None, str]:
    """Scorer-side gate on the gait parameters, against the trusted ranges.

    Returns a *rebuilt* dict holding exactly the eight parameters, so no other
    field in the submission can reach the simulator.
    """
    if not isinstance(obj, dict):
        return None, "submission must be a JSON object"

    ranges = cfg.get("ranges")
    if not isinstance(ranges, dict):
        return None, "trusted config has no 'ranges' section"

    clean: dict[str, float] = {}
    for key in PARAM_KEYS:
        if key not in obj:
            return None, f"missing key '{key}'"
        value = obj[key]
        # Explicit and ahead of the interval test: every comparison against NaN
        # is False, so an interval check alone rejects NaN for the wrong reason
        # and would silently admit it if the test were ever inverted.
        if not _finite_number(value):
            return None, f"key '{key}' must be a finite number, got {value!r}"
        try:
            lo, hi = (float(x) for x in ranges[key])
        except Exception:
            return None, f"trusted config has no bounds for {key}"
        val = float(value)
        ok = (lo <= val < hi) if key in HALF_OPEN_KEYS else (lo <= val <= hi)
        if not ok:
            closing = ")" if key in HALF_OPEN_KEYS else "]"
            return None, f"{key}={val:.6f} out of range [{lo}, {hi}{closing}"
        clean[key] = val

    return clean, "ok"


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
    cfg_src = benchmark_dir / "references" / "gait_config.json"
    model_src = benchmark_dir / "references" / "ant.xml"
    for required in (trusted_eval_src, cfg_src, model_src):
        if not required.is_file():
            return _bail(f"trusted asset not found: {required}")

    private = Path(tempfile.mkdtemp(prefix="fe_quadruped_trusted_")).resolve()
    try:
        # ------------------------------------------------------------ trusted
        # Everything in this block happens before the candidate is started.
        trusted_eval_bytes = trusted_eval_src.read_bytes()
        cfg_bytes = cfg_src.read_bytes()
        model_bytes = model_src.read_bytes()
        artifacts["trusted_evaluator_sha256"] = hashlib.sha256(trusted_eval_bytes).hexdigest()
        artifacts["trusted_config_sha256"] = hashlib.sha256(cfg_bytes).hexdigest()
        artifacts["trusted_model_sha256"] = hashlib.sha256(model_bytes).hexdigest()

        try:
            cfg = json.loads(cfg_bytes.decode("utf-8-sig"))
        except Exception as exc:
            return _bail(f"trusted config unreadable: {exc}")

        (private / "verification").mkdir(parents=True)
        (private / "references").mkdir(parents=True)
        private_eval = private / "verification" / "evaluator.py"
        private_eval.write_bytes(trusted_eval_bytes)
        (private / "references" / "gait_config.json").write_bytes(cfg_bytes)
        (private / "references" / "ant.xml").write_bytes(model_bytes)

        try:
            sandbox = _import_sandbox_helper(root)
            trusted = _load_trusted_scorer(private_eval)
        except Exception as exc:
            return _bail(f"failed to prepare trusted scoring context: {exc}")

        # ---------------------------------------------------------- candidate
        timeout_s = max(1.0, float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "240") or "240"))

        try:
            run = sandbox.run_candidate_isolated(
                program_path_p,
                # The published task tree puts `references/` next to the working
                # directory, so a candidate that reads the config keeps working.
                # It gets private copies; scoring uses the bytes captured above,
                # so tampering with them is pointless.
                inputs={
                    "references/gait_config.json": cfg_bytes,
                    "references/ant.xml": model_bytes,
                    # Seeded so a candidate that never writes still produces the
                    # expected output and we keep its return code (invariant 3)
                    # instead of losing it to a missing-output exception.
                    "submission.json": b"",
                },
                expected_outputs=("submission.json",),
                timeout_s=timeout_s,
                # Stage the candidate with its own reference copies so its
                # default import path points at that temporary workspace.
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

        params, reason = _validate_params(raw, cfg)
        if params is None:
            return _bail(f"invalid submission: {reason}")

        # -------------------------------------------------------------- score
        # Trusted rollout, trusted model, trusted config; candidate-supplied gait
        # parameters only.
        scoring_submission = private / "submission.json"
        scoring_submission.write_text(json.dumps(params), encoding="utf-8")

        try:
            raw_speed = float(trusted.evaluate(scoring_submission))
        except Exception as exc:
            return _bail(f"trusted scorer raised: {exc}")

        if not math.isfinite(raw_speed):
            return _bail(f"trusted scorer returned a non-finite speed: {raw_speed!r}")

        feasible = raw_speed > 0.0
        metrics["feasible"] = 1.0 if feasible else 0.0
        if not feasible:
            return _bail("infeasible gait")

        metrics["valid"] = 1.0
        metrics["speed_mps"] = raw_speed
        metrics["combined_score"] = raw_speed
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(private, ignore_errors=True)
