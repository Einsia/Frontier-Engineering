from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Scoring-relevant constants, owned by the scorer.
# ---------------------------------------------------------------------------
CANDIDATE_TIMEOUT_S = 300.0
OCTAVE_TIMEOUT_S = 300.0

PASS_BANNER = "=====结果文件全部检验通过====="
PAYLOAD_RE = re.compile(r"飞船运载质量：([0-9]+(?:\.[0-9]+)?)\s*kg")

RESULTS_COLUMNS = 10
RESULTS_MAX_ROWS = 100_000
RESULTS_MAX_BYTES = 32 << 20
RESULTS_ABS_LIMIT = 1e12

# Environment the candidate subprocess may see. Everything else is dropped, so
# the harness cannot hand the candidate a PYTHONPATH/PYTHONSTARTUP injection
# point, and the candidate cannot inherit scorer-only settings.
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
    if (path / "benchmarks").is_dir():
        return True
    return (path / "Astrodynamics").is_dir() and (path / "ElectronicDesignAutomation").is_dir()


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

    It lives outside every benchmark directory so that a ``copy_files.txt`` of
    ``.`` cannot drag it into a sandbox the candidate can write to.
    """
    shared = repo_root / "benchmarks" / "_shared"
    if not (shared / "candidate_sandbox.py").is_file():
        raise RuntimeError(f"shared isolation helper not found under {shared}")
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import candidate_sandbox  # noqa: PLC0415

    return candidate_sandbox


def _tail(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _truncate_middle(text: str, limit: int = 200_000) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, (limit - 128) // 2)
    omitted = len(text) - (2 * keep)
    return text[:keep] + f"\n\n[... truncated {omitted} chars ...]\n\n" + text[-keep:]


def _resolve_octave_executable() -> str | None:
    candidate_paths: list[Path] = []
    seen: set[str] = set()

    for env_name in (
        "FRONTIER_EVAL_UNIFIED_OCTAVE_EXECUTABLE",
        "FRONTIER_EVAL_UNIFIED_OCTAVE",
        "OCTAVE",
    ):
        raw = str(os.environ.get(env_name, "") or "").strip()
        if raw:
            candidate_paths.append(Path(raw).expanduser())

    for prefix_raw in (os.environ.get("CONDA_PREFIX", ""), sys.prefix):
        prefix = str(prefix_raw or "").strip()
        if not prefix:
            continue
        prefix_path = Path(prefix).expanduser()
        candidate_paths.append(prefix_path / "bin" / "octave-cli")
        candidate_paths.append(prefix_path / "bin" / "octave")

    for name in ("octave-cli", "octave"):
        resolved = shutil.which(name)
        if resolved:
            candidate_paths.append(Path(resolved).expanduser())

    for candidate in candidate_paths:
        path = candidate.expanduser()
        if not path.is_absolute():
            path = path.resolve()
        key = os.path.realpath(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def _octave_support_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    prefix_candidates = (
        os.environ.get("OCTAVE_HOME", ""),
        os.environ.get("CONDA_PREFIX", ""),
        sys.prefix,
    )
    for raw_prefix in prefix_candidates:
        prefix = str(raw_prefix or "").strip()
        if not prefix:
            continue
        prefix_path = Path(prefix).expanduser()
        for candidate in sorted((prefix_path / "share" / "octave").glob("*/m")):
            key = candidate.as_posix()
            if key in seen or not candidate.is_dir():
                continue
            seen.add(key)
            roots.append(candidate)
        site_m = prefix_path / "share" / "octave" / "site" / "m"
        key = site_m.as_posix()
        if key not in seen and site_m.is_dir():
            seen.add(key)
            roots.append(site_m)
    return roots


def _validate_results_text(raw: bytes) -> tuple[str, str | None]:
    """Scorer-side check that results.txt is a plain numeric table.

    The Octave validator is handed this file as *data*. Nothing here can make
    Octave run candidate-authored code, but a malformed table would otherwise
    surface as an opaque Octave failure, and an unbounded one is a cheap way to
    burn the evaluation budget.
    """
    if len(raw) > RESULTS_MAX_BYTES:
        return "", f"results.txt too large ({len(raw)} bytes)"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return "", f"results.txt is not valid UTF-8: {exc}"

    rows: list[list[float]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != RESULTS_COLUMNS:
            return "", (
                f"results.txt line {lineno} has {len(parts)} fields, expected {RESULTS_COLUMNS}"
            )
        try:
            values = [float(p) for p in parts]
        except ValueError:
            return "", f"results.txt line {lineno} contains a non-numeric field"
        if not all(np.isfinite(v) for v in values):
            return "", f"results.txt line {lineno} contains a non-finite value"
        if any(abs(v) > RESULTS_ABS_LIMIT for v in values):
            return "", f"results.txt line {lineno} contains an out-of-range value"
        rows.append(values)
        if len(rows) > RESULTS_MAX_ROWS:
            return "", f"results.txt has more than {RESULTS_MAX_ROWS} rows"

    if not rows:
        return "", "results.txt is empty"
    return text, None


def evaluate(program_path: str, *, repo_root: Path | None = None):
    """
    Evaluator for benchmarks/Astrodynamics/MannedLunarLanding.

    - Runs the candidate in an isolated subprocess whose only output is
      `results.txt` -- a numeric table, never code.
    - Re-runs the Octave validator `aerodynamics_check_octave_full.m` in a
      *separate, scorer-owned* directory that contains nothing but that table.
    - Parses `outputlog.txt` for pass/fail and payload.

    Why the two directories are separate: Octave resolves function names against
    the current directory *before* the addpath'd validator directory, and it
    sources `.octaverc` from the current directory at startup. Sharing one
    working directory between the candidate and the validator therefore let a
    candidate replace the validator outright (measured: payload 999999 kg from a
    six-line `aerodynamics_check_octave_full.m`, and 888888 kg from a
    `.octaverc`, against an honest baseline of 4577.44 kg).
    """
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program_path = str(Path(program_path).expanduser().resolve())

    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "payload_kg": 0.0,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }
    artifacts: dict[str, str] = {}

    # Everything the scorer needs must be resident before the candidate runs.
    try:
        sandbox = _import_isolation(repo_root)
    except Exception as e:
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = _tail(traceback.format_exc())
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    eval_dir = (repo_root / "benchmarks" / "Astrodynamics" / "MannedLunarLanding" / "eval").resolve()
    if not eval_dir.is_dir():
        eval_dir = (repo_root / "Astrodynamics" / "MannedLunarLanding" / "eval").resolve()
    if not eval_dir.is_dir():
        artifacts["error_message"] = f"eval dir not found: {eval_dir}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    octave_executable = _resolve_octave_executable()
    if not octave_executable:
        artifacts["error_message"] = "octave executable not found"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    support_roots = _octave_support_roots()

    # ---------------------------------------------------------------- 1) run
    # The candidate produces data. It gets its own throwaway directory, which is
    # destroyed before the validator ever starts.
    try:
        run = sandbox.run_candidate_isolated(
            Path(program_path),
            expected_outputs=("results.txt",),
            timeout_s=CANDIDATE_TIMEOUT_S,
            copy_into_workdir=True,
            env_allowlist=CANDIDATE_ENV_ALLOWLIST,
            rlimits=CANDIDATE_RLIMITS,
            python=sys.executable,
        )
    except sandbox.InvalidSubmissionError as e:
        artifacts["error_message"] = str(e)
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    except Exception as e:
        artifacts["error_message"] = f"failed to run candidate: {e}"
        artifacts["traceback"] = _tail(traceback.format_exc())
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    artifacts["program_stdout"] = _tail(run.stdout_tail)
    artifacts["program_stderr"] = _tail(run.stderr_tail)
    artifacts["program_stdout_full"] = _truncate_middle(run.stdout_tail)
    artifacts["program_stderr_full"] = _truncate_middle(run.stderr_tail)
    metrics["program_returncode"] = float(run.returncode)

    if run.timed_out:
        artifacts["error_message"] = f"program timeout after {CANDIDATE_TIMEOUT_S}s"
        metrics["timeout"] = 1.0
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    # A non-zero return code is always a failure, even if results.txt survived.
    if run.returncode != 0:
        artifacts["error_message"] = f"candidate program exited non-zero ({run.returncode})"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    results_text, results_error = _validate_results_text(run.read_output_bytes("results.txt"))
    if results_error is not None:
        artifacts["error_message"] = f"invalid results.txt: {results_error}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    artifacts["results.txt"] = results_text

    # ------------------------------------------------------------ 2) validate
    validate_dir = Path(tempfile.mkdtemp(prefix="fe_mll_validate_")).resolve()
    try:
        # The validation directory is created by the scorer and holds exactly one
        # file: the candidate's data. No candidate-written `.m`, no `.octaverc`,
        # no pre-seeded outputlog.txt can exist here.
        (validate_dir / "results.txt").write_text(results_text, encoding="utf-8")

        fake_home = validate_dir / "_home"
        fake_home.mkdir()

        octave_prelude = [f"addpath(genpath('{root.as_posix()}')); " for root in support_roots]
        octave_prelude.append(f"addpath('{eval_dir.as_posix()}'); ")
        octave_expr = "".join(octave_prelude) + "aerodynamics_check_octave_full; "

        octave_cmd = [octave_executable]
        if not Path(octave_executable).name.startswith("octave-cli"):
            octave_cmd.append("--no-gui")
        # --norc: do not read ~/.octaverc, ./.octaverc or the site-wide octaverc.
        octave_cmd.extend(["--norc", "--quiet", "--eval", octave_expr])
        artifacts["octave_executable"] = octave_executable
        artifacts["octave_command"] = " ".join(octave_cmd)

        octave_env = {
            k: v
            for k, v in os.environ.items()
            if k in ("PATH", "LANG", "LC_ALL", "OCTAVE_HOME", "CONDA_PREFIX", "TERM")
        }
        # A scorer-owned HOME, so a candidate that ran earlier in this evaluation
        # cannot reach the validator through ~/.octaverc. Directly exec the
        # binary rather than going through a login shell, which would source
        # ~/.bash_profile for the same reason.
        octave_env["HOME"] = str(fake_home)
        octave_env["OCTAVE_HISTFILE"] = str(validate_dir / "_history")

        try:
            proc2 = subprocess.run(
                octave_cmd,
                cwd=str(validate_dir),
                capture_output=True,
                text=True,
                timeout=OCTAVE_TIMEOUT_S,
                env=octave_env,
            )
        except FileNotFoundError as e:
            artifacts["error_message"] = f"octave not found: {e}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        except subprocess.TimeoutExpired as e:
            artifacts["error_message"] = f"octave timeout: {e}"
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        artifacts["octave_stdout"] = _tail(proc2.stdout)
        artifacts["octave_stderr"] = _tail(proc2.stderr)
        artifacts["octave_stdout_full"] = _truncate_middle(proc2.stdout)
        artifacts["octave_stderr_full"] = _truncate_middle(proc2.stderr)
        metrics["octave_returncode"] = float(proc2.returncode)

        log_path = validate_dir / "outputlog.txt"
        log_text = ""
        if log_path.is_file():
            try:
                log_text = log_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                log_text = ""
        if log_text:
            artifacts["outputlog.txt"] = log_text
        artifacts["outputlog_tail"] = _tail(log_text)

        # `diary` mirrors the validator's stdout into outputlog.txt, so the two
        # must agree. They can only disagree if something other than the
        # validator wrote the log, which the scorer-owned directory rules out --
        # the cross-check is cheap insurance, not the primary defence.
        passed_log = PASS_BANNER in log_text
        passed_stdout = PASS_BANNER in proc2.stdout
        metrics["banner_agreement"] = 1.0 if passed_log == passed_stdout else 0.0
        if passed_log != passed_stdout:
            artifacts["error_message"] = (
                "octave log and stdout disagree on the validation banner"
            )
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        payload = 0.0
        if passed_log:
            match = PAYLOAD_RE.search(log_text)
            if match is None:
                artifacts["error_message"] = "validator passed but reported no payload mass"
                metrics["runtime_s"] = float(time.time() - start)
                return _wrap(metrics, artifacts)
            payload = float(match.group(1))
            if not np.isfinite(payload) or payload < 0.0:
                artifacts["error_message"] = f"validator reported an invalid payload: {payload}"
                metrics["runtime_s"] = float(time.time() - start)
                return _wrap(metrics, artifacts)

        metrics["payload_kg"] = float(payload)
        metrics["runtime_s"] = float(time.time() - start)
        if passed_log:
            metrics["combined_score"] = float(payload)
            metrics["valid"] = 1.0
        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(validate_dir, ignore_errors=True)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
