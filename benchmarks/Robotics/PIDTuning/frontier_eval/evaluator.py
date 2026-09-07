"""Hardened unified evaluator for Robotics/PIDTuning.

What was wrong
--------------
This task already got the hard part right: the candidate ran as a subprocess and
returned only ``submission.json``, and ``verification/evaluator.py`` owns a
genuinely good three-layer gate (keys present -> numeric -> inside the
configured range). What it got wrong was *ordering*. The old flow was::

    proc = subprocess.run([sys.executable, sandbox_program], ...)   # candidate
    ...
    spec.loader.exec_module(module)                                 # scorer
    raw_score = float(module.evaluate(sandbox_submission))          # config re-read

Both the scoring module and the graded instance were fetched from the benchmark
tree *after* the candidate had had a turn on the same filesystem. That is
invariant 1 of ``benchmarks/_shared/candidate_sandbox`` violated, and both halves
were confirmed exploitable against the old file:

1. **Scorer loaded from a path the candidate had just written.** A candidate
   whose body was ``(repo/verification/evaluator.py).write_text(
   "def evaluate(p): return 999.0")`` plus a junk ``{"junk": 1}`` submission was
   graded by its own code: ``combined_score`` 0.036626766599899996 (honest
   baseline) -> **999.0**.
2. **Graded instance supplied by the candidate.** ``load_config()`` resolves
   ``references/pid_config.json`` from ``__file__``, i.e. re-reads it at scoring
   time. A candidate that replaced ``scenarios`` with a single 0.5 s hover
   starting 1 mm off target -- and submitted the *stock* baseline gains --
   scored **11683.569318244708**, because the score is a geometric mean of
   1/ITAE and ITAE shrinks with the horizon.

The fix
-------
* The trusted config bytes are read and ``verification/evaluator.py`` is
  exec_module'd (numpy included) **before** the candidate is started, from the
  pristine benchmark directory. Scoring afterwards uses only those in-memory
  objects, so what the candidate does to the tree is irrelevant to its own score.
* The candidate runs via ``candidate_sandbox.run_candidate_isolated``: its own
  process, a scrubbed environment, resource limits, and a hard timeout. It never
  enters this process, so it cannot rebind ``simulate_quadrotor_2d``.
* The 12 gains are re-validated here, on the scorer's side, against the trusted
  bounds, with an explicit finite/non-bool check ahead of the interval test --
  ``lo <= NaN <= hi`` is False, so NaN was already rejected, but by accident
  rather than on purpose.

Deliberately unchanged: ``verification/evaluator.py`` is byte-for-byte the same
file. The quadrotor integration, the pitch-limit hard gate, the ITAE objective
and the geometric mean all still live there and are still the only thing that
produces a number. An honest candidate's score is bit-identical to the
pre-hardening value (0.036626766599899996 for ``scripts/init.py``).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

INVALID_COMBINED_SCORE = -1e18

TASK_NAME = "PIDTuning"

GAIN_KEYS = (
    "Kp_z", "Ki_z", "Kd_z", "N_z",
    "Kp_x", "Ki_x", "Kd_x", "N_x",
    "Kp_theta", "Ki_theta", "Kd_theta", "N_theta",
)

# Same mapping the trusted evaluator uses; duplicated here so the scorer-side
# bounds check does not depend on a private name in the trusted module.
KEY_TO_GROUP = {
    "Kp_z": ("altitude", "Kp"), "Ki_z": ("altitude", "Ki"),
    "Kd_z": ("altitude", "Kd"), "N_z": ("altitude", "N"),
    "Kp_x": ("horizontal", "Kp"), "Ki_x": ("horizontal", "Ki"),
    "Kd_x": ("horizontal", "Kd"), "N_x": ("horizontal", "N"),
    "Kp_theta": ("pitch", "Kp"), "Ki_theta": ("pitch", "Ki"),
    "Kd_theta": ("pitch", "Kd"), "N_theta": ("pitch", "N"),
}

MAX_SUBMISSION_BYTES = 1 * 1024 * 1024

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
    """exec_module the *pristine* verification module, before the candidate runs.

    This is a scorer-owned file, never a candidate-owned one; the whole point of
    the ordering is that nothing the candidate does can change what lands here.
    """
    spec = importlib.util.spec_from_file_location("fe_pid_tuning_trusted_eval", evaluator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load trusted evaluator: {evaluator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for required in ("compute_itae", "simulate_quadrotor_2d"):
        if not hasattr(module, required):
            raise RuntimeError(f"trusted evaluator defines no {required}(): {evaluator_path}")
    return module


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _validate_gains(obj: Any, cfg: dict[str, Any]) -> tuple[dict[str, float] | None, str]:
    """Scorer-side gate on the candidate's gains, against the trusted bounds.

    Returns a *rebuilt* dict holding exactly the twelve gains, so no other field
    in the submission can reach the simulator.
    """
    if not isinstance(obj, dict):
        return None, "submission must be a JSON object"

    ranges = cfg.get("gains")
    if not isinstance(ranges, dict):
        return None, "trusted config has no 'gains' section"

    clean: dict[str, float] = {}
    for key in GAIN_KEYS:
        if key not in obj:
            return None, f"missing key '{key}'"
        value = obj[key]
        # Explicit and ahead of the interval test: every comparison against NaN
        # is False, so an interval check alone rejects NaN for the wrong reason
        # and would silently admit it if the test were ever inverted.
        if not _finite_number(value):
            return None, f"key '{key}' must be a finite number, got {value!r}"
        group, param = KEY_TO_GROUP[key]
        try:
            lo, hi = (float(x) for x in ranges[group][param])
        except Exception:
            return None, f"trusted config has no bounds for {key}"
        val = float(value)
        if not (lo <= val <= hi):
            return None, f"{key}={val:.6f} out of range [{lo}, {hi}]"
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

    # ---------------------------------------------------------------- trusted
    # Everything in this block happens before the candidate is started.
    cfg_src = benchmark_dir / "references" / "pid_config.json"
    trusted_eval_src = benchmark_dir / "verification" / "evaluator.py"
    if not cfg_src.is_file():
        return _bail(f"pid config not found: {cfg_src}")
    if not trusted_eval_src.is_file():
        return _bail(f"trusted evaluator not found: {trusted_eval_src}")

    cfg_bytes = cfg_src.read_bytes()
    artifacts["trusted_config_sha256"] = hashlib.sha256(cfg_bytes).hexdigest()
    artifacts["trusted_evaluator_sha256"] = hashlib.sha256(trusted_eval_src.read_bytes()).hexdigest()

    try:
        cfg = json.loads(cfg_bytes.decode("utf-8-sig"))
    except Exception as exc:
        return _bail(f"trusted config unreadable: {exc}")

    try:
        sandbox = _import_sandbox_helper(root)
        trusted = _load_trusted_scorer(trusted_eval_src)
    except Exception as exc:
        return _bail(f"failed to prepare trusted scoring context: {exc}")

    # -------------------------------------------------------------- candidate
    timeout_s = max(1.0, float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "240") or "240"))

    try:
        run = sandbox.run_candidate_isolated(
            program_path_p,
            # The published contract is that the optimizer can read the config
            # from `references/` next to itself. It gets a private copy; scoring
            # uses `cfg_bytes` captured above, so tampering with it is pointless.
            inputs={
                "references/pid_config.json": cfg_bytes,
                # Seeded so a candidate that never writes still produces the
                # expected output and we keep its return code (invariant 3)
                # instead of losing it to a missing-output exception.
                "submission.json": b"",
            },
            expected_outputs=("submission.json",),
            timeout_s=timeout_s,
            # Copy into the sandbox: keeps sys.path[0] and __file__ inside a
            # directory holding nothing but the candidate and its own config.
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

    gains, reason = _validate_gains(raw, cfg)
    if gains is None:
        return _bail(f"invalid submission: {reason}")

    # ------------------------------------------------------------------ score
    # Trusted simulator, trusted scenarios, candidate-supplied gains only.
    try:
        raw_score = float(trusted.compute_itae(gains, cfg))
    except Exception as exc:
        return _bail(f"trusted scorer raised: {exc}")

    if not math.isfinite(raw_score):
        return _bail(f"trusted scorer returned a non-finite score: {raw_score!r}")

    feasible = raw_score > 0.0
    metrics["feasible"] = 1.0 if feasible else 0.0
    if not feasible:
        return _bail("infeasible PID gains")

    metrics["valid"] = 1.0
    metrics["combined_score"] = raw_score
    metrics["runtime_s"] = float(time.time() - start)
    return _wrap(metrics, artifacts)
