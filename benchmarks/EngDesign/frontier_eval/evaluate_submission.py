from __future__ import annotations

import argparse
import contextlib
import hmac
import importlib.util
import io
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

TASK_IDS: tuple[str, ...] = (
    "AM_02",
    "AM_03",
    "CY_03",
    "WJ_01",
    "XY_05",
    "YJ_02",
    "YJ_03",
)

# Bound source and serialized submission size in the candidate subprocess.
MAX_CANDIDATE_BYTES = 8 * 1024 * 1024

SUBMISSION_NAMES: tuple[str, ...] = ("SUBMISSION", "submission", "ENGDESIGN_SUBMISSION")

# Per-task scores are documented as percentages; clamp so that a task-local
# compromise (e.g. CY_03/WJ_01 execute candidate-supplied source by design)
# cannot inflate `combined_score` beyond one task's legitimate share.
SCORE_MIN = 0.0
SCORE_MAX = 100.0


class SubmissionFormatError(ValueError):
    """Raised when the candidate file is not a readable submission."""


def _tail(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except Exception:
            return default
    return default


def _clamp_score(value: Any, default: float = 0.0) -> float:
    raw = _safe_float(value, default=default)
    if raw != raw:  # NaN
        return default
    if raw < SCORE_MIN:
        return SCORE_MIN
    if raw > SCORE_MAX:
        return SCORE_MAX
    return raw


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _resolve_output_path(base_dir: Path, value: str) -> Path:
    p = Path(value).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (base_dir / p).resolve()


def _resolve_candidate_path(base_dir: Path, value: str) -> Path:
    p = Path(value).expanduser()
    if p.is_absolute():
        return p.resolve()
    cwd_path = p.resolve()
    if cwd_path.exists():
        return cwd_path
    return (base_dir / p).resolve()


@contextlib.contextmanager
def _pushd(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _load_module(module_name: str, module_path: Path, extra_paths: list[Path]) -> Any:
    original_sys_path = list(sys.path)
    previous_module = sys.modules.get(module_name)
    try:
        sys.path = [str(p) for p in extra_paths] + original_sys_path
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module spec from: {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_sys_path
        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module


def _validate_submission_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SubmissionFormatError("SUBMISSION must be a JSON-compatible dict")
    try:
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise SubmissionFormatError(f"Invalid submission data: {exc}") from exc
    missing = [t for t in TASK_IDS if t not in value]
    if missing:
        raise SubmissionFormatError(
            f"SUBMISSION is missing required task keys: {', '.join(missing)}"
        )
    return value


def _load_submission(candidate_path: Path) -> dict[str, Any]:
    """Read JSON directly or evaluate Python SUBMISSION in a restricted child."""
    if not candidate_path.is_file():
        raise SubmissionFormatError(f"Candidate file not found: {candidate_path}")

    size = candidate_path.stat().st_size
    if size > MAX_CANDIDATE_BYTES:
        raise SubmissionFormatError(
            f"Candidate file is too large ({size} bytes > {MAX_CANDIDATE_BYTES})."
        )

    try:
        text = candidate_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SubmissionFormatError(f"Candidate file is not valid UTF-8: {exc}") from exc

    if candidate_path.suffix.lower() in {".json", ".json5"}:
        try:
            payload = json.loads(text)
        except Exception as exc:
            raise SubmissionFormatError(f"Candidate JSON is invalid: {exc}") from exc
        if isinstance(payload, dict):
            for key in SUBMISSION_NAMES:
                inner = payload.get(key)
                if isinstance(inner, dict):
                    return _validate_submission_payload(inner)
            return _validate_submission_payload(payload)
        raise SubmissionFormatError("Candidate JSON must contain a top-level object.")

    shared = next((parent / "benchmarks" / "_shared" for parent in Path(__file__).resolve().parents
                   if (parent / "benchmarks" / "_shared" / "candidate_sandbox.py").is_file()), None)
    if shared is None:
        raise SubmissionFormatError("candidate isolation helper not found")
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import candidate_sandbox as sandbox
    runner = """import json, runpy
from pathlib import Path
scope = runpy.run_path('candidate.py', run_name='engdesign_candidate')
for name in ('SUBMISSION', 'submission', 'ENGDESIGN_SUBMISSION'):
    if name in scope:
        Path('submission.json').write_text(json.dumps(scope[name], allow_nan=False))
        break
else:
    raise ValueError('Candidate must define SUBMISSION')
"""
    with tempfile.TemporaryDirectory(prefix="fe_engdesign_runner_") as tmp:
        wrapper = Path(tmp) / "runner.py"
        wrapper.write_text(runner)
        try:
            run = sandbox.run_candidate_isolated(
                wrapper, inputs={"candidate.py": text.encode()},
                expected_outputs=("submission.json",), timeout_s=60,
                readonly_paths=(), env_allowlist=("PATH", "LANG", "LC_ALL"),
                rlimits={"FSIZE": MAX_CANDIDATE_BYTES},
            )
            if not run.ok:
                raise SubmissionFormatError(f"Candidate failed: {run.stderr_tail}")
            value = sandbox.load_json_output(run)
        except sandbox.InvalidSubmissionError as exc:
            raise SubmissionFormatError(str(exc)) from exc
    return _validate_submission_payload(value)


def _normalize_payload(task_id: str, section: Any) -> dict[str, Any]:
    if not isinstance(section, dict):
        raise TypeError(f"`SUBMISSION[{task_id}]` must be a dict")

    if "config" in section and isinstance(section.get("config"), dict):
        payload = dict(section)
    else:
        config = {k: v for k, v in section.items() if k != "reasoning"}
        payload = {
            "reasoning": str(section.get("reasoning", "")),
            "config": config,
        }

    payload.setdefault("reasoning", "")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise TypeError(f"`SUBMISSION[{task_id}].config` must be a dict")

    if task_id == "CY_03":
        if "vioblk_read" not in config and "vioblk_read_code" in config:
            config["vioblk_read"] = config["vioblk_read_code"]
        if "vioblk_write" not in config and "vioblk_write_code" in config:
            config["vioblk_write"] = config["vioblk_write_code"]
        read_code = str(config.get("vioblk_read", "") or "")
        write_code = str(config.get("vioblk_write", "") or "")
        banned_tokens = (
            "gold_vioblk_read",
            "gold_vioblk_write",
            "globals()[\"gold_vioblk_read\"]",
            "globals()[\"gold_vioblk_write\"]",
            "globals()['gold_vioblk_read']",
            "globals()['gold_vioblk_write']",
        )
        joined = f"{read_code}\n{write_code}"
        for token in banned_tokens:
            if token in joined:
                raise ValueError(
                    "CY_03 submission references forbidden gold helper functions."
                )

    payload["config"] = config
    return payload


def _evaluate_single_task(
    *,
    task_id: str,
    benchmark_dir: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    start = time.time()
    task_dir = (benchmark_dir / task_id).resolve()
    result: dict[str, Any] = {
        "task_id": task_id,
        "passed": False,
        "score": 0.0,
        "confidence": 0.0,
        "task_valid": 0.0,
        "details": {},
        "error": "",
    }

    try:
        if not task_dir.is_dir():
            raise FileNotFoundError(f"Task directory not found: {task_dir}")
        if not candidate_path.is_file():
            raise FileNotFoundError(f"Candidate file not found: {candidate_path}")

        submission = _load_submission(candidate_path)
        if task_id not in submission:
            raise KeyError(f"Missing task key in SUBMISSION: {task_id}")
        payload = _normalize_payload(task_id, submission[task_id])

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            output_module = _load_module(
                module_name=f"engdesign_{task_id.lower()}_output",
                module_path=task_dir / "output_structure.py",
                extra_paths=[task_dir, benchmark_dir],
            )
            evaluate_module = _load_module(
                module_name=f"engdesign_{task_id.lower()}_evaluate",
                module_path=task_dir / "evaluate.py",
                extra_paths=[task_dir, benchmark_dir],
            )

            if not hasattr(output_module, "Response_structure"):
                raise AttributeError(f"{task_id}/output_structure.py has no Response_structure")
            if not hasattr(evaluate_module, "evaluate_llm_response"):
                raise AttributeError(f"{task_id}/evaluate.py has no evaluate_llm_response")

            response = output_module.Response_structure(**payload)
            with _pushd(task_dir):
                passed, details, score, confidence = evaluate_module.evaluate_llm_response(response)

        result["passed"] = bool(passed)
        result["score"] = _clamp_score(score, default=0.0)
        result["confidence"] = _clamp_score(confidence, default=0.0)
        result["task_valid"] = 1.0
        result["details"] = details if details is not None else {}
        result["eval_stdout"] = _tail(stdout_buf.getvalue(), limit=12000)
        result["eval_stderr"] = _tail(stderr_buf.getvalue(), limit=12000)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = _tail(traceback.format_exc(), limit=12000)

    result["runtime_s"] = float(time.time() - start)
    return result


def _default_failed_task_result(task_id: str, reason: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "passed": False,
        "score": 0.0,
        "confidence": 0.0,
        "task_valid": 0.0,
        "details": {},
        "error": reason,
    }


# ---------------------------------------------------------------------------
# Per-run result channel
# Results are written to --result-out with a token supplied by the parent over
# stdin. The child consumes the token before importing task modules. Candidate
# stdout is diagnostic output and does not supply the result record.
# This token is an integrity check, not an OS isolation boundary.
# ---------------------------------------------------------------------------

_RESULT_TOKEN: str | None = None


def _consume_launch_token() -> None:
    """Read the one-shot token from stdin and close stdin, before any task code."""
    global _RESULT_TOKEN
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
        token = payload.get("token") if isinstance(payload, dict) else None
        _RESULT_TOKEN = str(token) if isinstance(token, str) else None
    except Exception:
        _RESULT_TOKEN = None
    finally:
        with contextlib.suppress(Exception):
            sys.stdin.close()
        with contextlib.suppress(Exception):
            devnull = os.open(os.devnull, os.O_RDONLY)
            if devnull != 0:
                os.dup2(devnull, 0)
                os.close(devnull)
        with contextlib.suppress(Exception):
            sys.stdin = open(os.devnull, "r")  # noqa: SIM115


def _write_result_file(path: Path, token: str | None, result: dict[str, Any]) -> None:
    envelope = {"token": token, "result": result}
    tmp = path.with_name(path.name + ".partial")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(envelope, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _read_result_file(path: Path, token: str) -> tuple[dict[str, Any] | None, str]:
    if not path.is_file():
        return None, "child produced no result file"
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"result file is not valid JSON: {exc}"
    if not isinstance(envelope, dict):
        return None, "result file is not a JSON object"
    got = envelope.get("token")
    if not isinstance(got, str) or not hmac.compare_digest(got, token):
        return None, "result file token mismatch (forged or truncated result)"
    result = envelope.get("result")
    if not isinstance(result, dict):
        return None, "result file has no result object"
    return result, ""


def _run_full_evaluation(
    *,
    benchmark_dir: Path,
    candidate_path: Path,
    metrics_out: Path,
    artifacts_out: Path,
    task_timeout_s: float,
) -> None:
    start = time.time()
    hard_failures: list[str] = []
    task_results: dict[str, dict[str, Any]] = {}

    # Static pre-check only. `_load_submission` parses literals and executes
    # nothing, so this no longer hands the orchestrator process (which owns
    # subprocess dispatch, result parsing and metrics.json) to the candidate.
    # Each child re-reads the file independently anyway.
    try:
        _load_submission(candidate_path)
    except Exception as exc:
        metrics = {
            "combined_score": 0.0,
            "avg_score": 0.0,
            "valid": 0.0,
            "pass_rate": 0.0,
            "passed_tasks": 0.0,
            "total_tasks": float(len(TASK_IDS)),
            "task_valid_rate": 0.0,
            "hard_failures": 1.0,
            "runtime_s": float(time.time() - start),
        }
        artifacts = {
            "candidate_path": str(candidate_path),
            "benchmark_dir": str(benchmark_dir),
            "error_message": f"Failed to load candidate submission: {exc}",
            "traceback": _tail(traceback.format_exc(), limit=12000),
        }
        _write_json(metrics_out, metrics)
        _write_json(artifacts_out, artifacts)
        print(json.dumps({"combined_score": 0.0, "valid": 0.0, "error": str(exc)}, ensure_ascii=False))
        return

    self_path = Path(__file__).resolve()
    with tempfile.TemporaryDirectory(prefix="engdesign_results_") as result_dir_name:
        result_dir = Path(result_dir_name)
        for task_id in TASK_IDS:
            token = secrets.token_hex(32)
            result_path = result_dir / f"{task_id}_{secrets.token_hex(8)}.json"
            cmd = [
                sys.executable,
                str(self_path),
                "--single-task",
                task_id,
                "--candidate",
                str(candidate_path),
                "--benchmark-dir",
                str(benchmark_dir),
                "--result-out",
                str(result_path),
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    input=json.dumps({"token": token}),
                    capture_output=True,
                    text=True,
                    timeout=max(5.0, float(task_timeout_s)),
                )
            except subprocess.TimeoutExpired as exc:
                reason = f"TimeoutExpired: {exc}"
                hard_failures.append(f"{task_id}: {reason}")
                task_results[task_id] = _default_failed_task_result(task_id, reason)
                continue
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                hard_failures.append(f"{task_id}: {reason}")
                task_results[task_id] = _default_failed_task_result(task_id, reason)
                continue

            parsed, read_error = _read_result_file(result_path, token)
            if proc.returncode != 0 or parsed is None:
                reason = (
                    f"single-task process failed (rc={proc.returncode}, "
                    f"result_channel={read_error or 'ok'}). "
                    f"stdout_tail={_tail(proc.stdout or '', 1500)!r} "
                    f"stderr_tail={_tail(proc.stderr or '', 1500)!r}"
                )
                hard_failures.append(f"{task_id}: {reason}")
                task_results[task_id] = _default_failed_task_result(task_id, reason)
                continue

            # Identity of the result is decided here, not by the child.
            parsed["task_id"] = task_id
            parsed.setdefault("passed", False)
            parsed["score"] = _clamp_score(parsed.get("score"), default=0.0)
            parsed["confidence"] = _clamp_score(parsed.get("confidence"), default=0.0)
            parsed.setdefault("task_valid", 0.0)
            if proc.stdout:
                parsed["runner_stdout"] = _tail(proc.stdout, limit=4000)
            if proc.stderr:
                parsed["runner_stderr"] = _tail(proc.stderr, limit=4000)
            task_results[task_id] = parsed

    metrics: dict[str, float] = {}
    score_sum = 0.0
    passed_sum = 0.0
    task_valid_sum = 0.0
    total_tasks = float(len(TASK_IDS))

    for task_id in TASK_IDS:
        result = task_results.get(task_id)
        if not isinstance(result, dict):
            result = _default_failed_task_result(task_id, "missing task result")
            task_results[task_id] = result

        score_v = _clamp_score(result.get("score"), default=0.0)
        passed_v = 1.0 if bool(result.get("passed")) else 0.0
        task_valid_v = _safe_float(result.get("task_valid"), default=0.0)

        score_sum += score_v
        passed_sum += passed_v
        task_valid_sum += task_valid_v

        key = task_id.lower()
        metrics[f"{key}_score"] = score_v
        metrics[f"{key}_passed"] = passed_v
        metrics[f"{key}_valid"] = task_valid_v

    combined_score = score_sum / total_tasks if total_tasks > 0 else 0.0
    pass_rate = passed_sum / total_tasks if total_tasks > 0 else 0.0
    task_valid_rate = task_valid_sum / total_tasks if total_tasks > 0 else 0.0

    metrics.update(
        {
            "combined_score": combined_score,
            "avg_score": combined_score,
            "valid": 1.0 if (not hard_failures and task_valid_rate > 0.0) else 0.0,
            "pass_rate": pass_rate,
            "passed_tasks": passed_sum,
            "total_tasks": total_tasks,
            "task_valid_rate": task_valid_rate,
            "hard_failures": float(len(hard_failures)),
            "runtime_s": float(time.time() - start),
        }
    )

    if hard_failures:
        metrics["combined_score"] = 0.0
        metrics["avg_score"] = 0.0

    artifacts = {
        "candidate_path": str(candidate_path),
        "benchmark_dir": str(benchmark_dir),
        "task_order": list(TASK_IDS),
        "task_timeout_s": float(task_timeout_s),
        "hard_failures": hard_failures,
        "task_results": task_results,
    }

    _write_json(metrics_out, metrics)
    _write_json(artifacts_out, artifacts)
    print(
        json.dumps(
            {
                "combined_score": metrics["combined_score"],
                "valid": metrics["valid"],
                "pass_rate": metrics["pass_rate"],
                "hard_failures": metrics["hard_failures"],
            },
            ensure_ascii=False,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate EngDesign unified submission.")
    parser.add_argument("--candidate", required=True, type=str)
    parser.add_argument("--benchmark-dir", default=".", type=str)
    parser.add_argument("--metrics-out", default="metrics.json", type=str)
    parser.add_argument("--artifacts-out", default="artifacts.json", type=str)
    parser.add_argument("--task-timeout-s", default=180.0, type=float)
    parser.add_argument("--single-task", choices=TASK_IDS, default=None)
    parser.add_argument(
        "--result-out",
        default=None,
        type=str,
        help=(
            "Single-task mode: write the result JSON here instead of stdout. "
            "The parent authenticates it with a token delivered over stdin."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.single_task and args.result_out:
        # Before importing any task module or touching candidate data.
        _consume_launch_token()

    benchmark_dir = Path(args.benchmark_dir).expanduser().resolve()
    candidate_path = _resolve_candidate_path(benchmark_dir, args.candidate)

    if args.single_task:
        result = _evaluate_single_task(
            task_id=str(args.single_task),
            benchmark_dir=benchmark_dir,
            candidate_path=candidate_path,
        )
        if args.result_out:
            _write_result_file(
                _resolve_output_path(benchmark_dir, args.result_out),
                _RESULT_TOKEN,
                result,
            )
        else:
            # Manual/debug invocation only; the orchestrator never reads stdout.
            print(json.dumps(result, ensure_ascii=False, default=str))
        return 0

    metrics_out = _resolve_output_path(benchmark_dir, args.metrics_out)
    artifacts_out = _resolve_output_path(benchmark_dir, args.artifacts_out)
    _run_full_evaluation(
        benchmark_dir=benchmark_dir,
        candidate_path=candidate_path,
        metrics_out=metrics_out,
        artifacts_out=artifacts_out,
        task_timeout_s=float(args.task_timeout_s),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
