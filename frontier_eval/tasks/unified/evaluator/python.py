from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ..spec import UnifiedTaskSpec

INVALID_COMBINED_SCORE = -1e18
_UV_ENV_PYTHON_PREFIX = "uv-env:"
_LEGACY_ENV_PYTHON_PREFIX = "conda-env:"


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


def _remaining_timeout(deadline_s: float) -> float:
    return max(1.0, float(deadline_s - time.time()))


@lru_cache(maxsize=32)
def _resolve_uv_env_dir(env_name: str, repo_root: str | None = None) -> str:
    env_root = str(os.environ.get("FRONTIER_EVAL_UV_ENVS_DIR", "")).strip()
    if env_root:
        root = Path(env_root).expanduser()
    elif repo_root:
        root = Path(repo_root).expanduser() / ".venvs"
    else:
        root = Path(".venvs")
    env_dir = (root / env_name).resolve()
    return str(env_dir)


def _extract_uv_env_name(python_path: str | None) -> str | None:
    if not python_path:
        return None
    if python_path.startswith(_UV_ENV_PYTHON_PREFIX):
        return python_path[len(_UV_ENV_PYTHON_PREFIX) :].strip() or None
    if python_path.startswith(_LEGACY_ENV_PYTHON_PREFIX):
        return python_path[len(_LEGACY_ENV_PYTHON_PREFIX) :].strip() or None
    return None


@lru_cache(maxsize=32)
def _resolve_runtime_python_path(python_path: str | None, repo_root: str | None = None) -> str | None:
    if not python_path:
        return None
    env_name = _extract_uv_env_name(python_path)
    if not env_name:
        return python_path

    env_dir = Path(_resolve_uv_env_dir(env_name, repo_root))
    resolved = env_dir / "bin" / "python"
    if not resolved.exists():
        raise RuntimeError(f"runtime env {env_name} does not exist or has no python: {resolved}")
    return str(resolved)


def _safe_slug(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return safe or "benchmark"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _read_json(path: Path) -> Any | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _maybe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None
    return None


def _extract_numeric_metrics(raw: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    metrics: dict[str, float] = {}
    non_numeric: dict[str, Any] = {}
    for key, value in raw.items():
        metric_v = _maybe_float(value)
        if metric_v is None:
            non_numeric[str(key)] = value
            continue
        metrics[str(key)] = float(metric_v)
    return metrics, non_numeric


def _parse_last_json_dict(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    for raw in reversed(text.splitlines()):
        line = raw.strip()
        if not line:
            continue
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _should_ignore_fingerprint_entry(root: Path, path: Path) -> bool:
    # Nothing is exempt. Bytecode caches used to be skipped here so that the
    # __pycache__ directories created during a run would not be reported as
    # readonly violations, but a stale .pyc shadows its .py at import time, so
    # skipping them left a place to hide a rewritten scorer. Evaluation runs now
    # set PYTHONDONTWRITEBYTECODE=1 (see _build_eval_env) and therefore produce
    # no caches of their own; any that appear were put there by the candidate.
    del root, path
    return False


def _fingerprint_path(path: Path) -> str:
    if not path.exists():
        return "__MISSING__"
    if path.is_file():
        return f"file:{_hash_file(path)}"

    if path.is_dir():
        h = hashlib.sha256()
        for child in sorted(path.rglob("*")):
            if _should_ignore_fingerprint_entry(path, child):
                continue
            rel = child.relative_to(path).as_posix()
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            if child.is_dir():
                h.update(b"dir\0")
                continue
            h.update(b"file\0")
            h.update(_hash_file(child).encode("utf-8"))
            h.update(b"\0")
        return f"dir:{h.hexdigest()}"
    return "__UNKNOWN__"


_OUT_OF_BOUNDS = "__OUT_OF_BOUNDS__"


def _resolve_readonly_target(root: Path, rel: str) -> Path | None:
    """Resolve a readonly_files entry, or None when it points outside the sandbox.

    readonly_files.txt is task-supplied data, so an entry such as ``../x`` or an
    absolute path would otherwise make the harness hash -- and compare -- files
    that do not belong to the run.
    """
    if rel == ".":
        return root
    target = (root / rel).resolve()
    return target if _is_within(target, root) else None


def _snapshot_readonly(root: Path, rel_paths: tuple[str, ...]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for rel in rel_paths:
        target = _resolve_readonly_target(root, rel)
        snapshot[rel] = _OUT_OF_BOUNDS if target is None else _fingerprint_path(target)
    return snapshot


def _check_readonly_violations(root: Path, before: dict[str, str]) -> list[str]:
    violations: list[str] = []
    for rel, old_fp in before.items():
        target = _resolve_readonly_target(root, rel)
        new_fp = _OUT_OF_BOUNDS if target is None else _fingerprint_path(target)
        if old_fp != new_fp:
            violations.append(rel)
    return violations


def _enforce_readonly(root: Path, rel_paths: tuple[str, ...]) -> list[tuple[Path, int]]:
    """Drop write permission on the readonly paths for the duration of the run.

    Fingerprinting alone only tells us afterwards that the scorer was rewritten,
    by which point the tampered code has already produced a score. Taking the
    write bit away first means the common case fails at the write instead.

    Returns the original modes so the caller can restore them; the sandbox is a
    temporary tree, but rmtree cannot remove entries from a directory it may not
    write to. Best effort: a path we cannot chmod is left to the fingerprint
    check, which still runs afterwards.
    """
    saved: list[tuple[Path, int]] = []
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    for rel in rel_paths:
        target = _resolve_readonly_target(root, rel)
        if target is None or not target.exists():
            continue
        # Deepest first, so a directory stays writable while its children change.
        entries = sorted(target.rglob("*"), reverse=True) if target.is_dir() else []
        for path in [*entries, target]:
            try:
                mode = path.stat().st_mode
                saved.append((path, stat.S_IMODE(mode)))
                path.chmod(stat.S_IMODE(mode) & ~write_bits)
            except OSError:
                continue
    return saved


def _restore_modes(saved: list[tuple[Path, int]]) -> None:
    # Shallowest first, so each directory is writable before its children.
    for path, mode in sorted(saved):
        try:
            path.chmod(mode)
        except OSError:
            continue


def _copy_selected_entries(
    *,
    benchmark_dir: Path,
    sandbox_benchmark: Path,
    copy_files: tuple[str, ...],
) -> tuple[list[str], list[str], list[str]]:
    copied_files: list[str] = []
    copied_dirs: list[str] = []
    missing: list[str] = []

    sandbox_benchmark.mkdir(parents=True, exist_ok=True)

    copy_whole = any(rel == "." for rel in copy_files)
    if copy_whole:
        shutil.copytree(benchmark_dir, sandbox_benchmark, dirs_exist_ok=True)
        copied_dirs.append(".")
        return copied_files, copied_dirs, missing

    for rel in copy_files:
        src = (benchmark_dir / rel).resolve()
        if not _is_within(src, benchmark_dir):
            missing.append(f"{rel} (outside benchmark dir)")
            continue
        if not src.exists():
            missing.append(rel)
            continue

        dst = (sandbox_benchmark / rel).resolve()
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
            copied_dirs.append(rel)
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied_files.append(rel)

    return copied_files, copied_dirs, missing


def _append_agent_context(spec: UnifiedTaskSpec, artifacts: dict[str, Any]) -> None:
    if spec.constraints_path is not None:
        artifacts["constraints_path"] = str(spec.constraints_path)
    if spec.constraints_text:
        artifacts["constraints"] = _truncate_middle(spec.constraints_text, limit=120_000)

    if not spec.agent_files:
        return

    artifacts["agent_files"] = "\n".join(spec.agent_files)
    for rel in spec.agent_files:
        src = (spec.benchmark_dir / rel).resolve()
        key_base = f"agent_file::{rel}"
        if not _is_within(src, spec.benchmark_dir):
            artifacts[f"{key_base}::error"] = "outside benchmark dir"
            continue

        if src.is_file():
            text = _read_text(src)
            if text is None:
                artifacts[f"{key_base}::error"] = "failed to read file"
            else:
                artifacts[key_base] = _truncate_middle(text)
            continue

        if src.is_dir():
            entries: list[str] = []
            for child in sorted(src.rglob("*")):
                if child.is_dir():
                    continue
                entries.append(child.relative_to(spec.benchmark_dir).as_posix())
                if len(entries) >= 500:
                    entries.append("... (truncated)")
                    break
            artifacts[f"{key_base}::dir_listing"] = "\n".join(entries)
            continue

        artifacts[f"{key_base}::error"] = "path not found"


def _collect_output_artifacts(
    *,
    sandbox_benchmark: Path,
    artifact_files: tuple[str, ...],
    artifacts: dict[str, Any],
) -> None:
    if not artifact_files:
        return

    def _collect_one(*, key_base: str, target: Path) -> None:
        if not _is_within(target, sandbox_benchmark):
            artifacts[f"{key_base}::error"] = "outside sandbox benchmark dir"
            return

        if target.is_file():
            text = _read_text(target)
            if text is None:
                artifacts[f"{key_base}::error"] = "failed to read file"
            else:
                artifacts[key_base] = _truncate_middle(text, limit=120_000)
            return

        if target.is_dir():
            entries: list[str] = []
            for child in sorted(target.rglob("*")):
                if child.is_dir():
                    continue
                entries.append(child.relative_to(sandbox_benchmark).as_posix())
                if len(entries) >= 500:
                    entries.append("... (truncated)")
                    break
            artifacts[f"{key_base}::dir_listing"] = "\n".join(entries)
            return

        artifacts[f"{key_base}::error"] = "path not found"

    def _has_glob(pattern: str) -> bool:
        return any(ch in pattern for ch in "*?[]")

    artifacts["artifact_files"] = "\n".join(artifact_files)
    for rel in artifact_files:
        key_base = f"collected_artifact::{rel}"
        if _has_glob(rel):
            try:
                matched = sorted(
                    (p.resolve() for p in sandbox_benchmark.glob(rel)),
                    key=lambda p: p.as_posix(),
                )
            except Exception:
                artifacts[f"{key_base}::error"] = "invalid glob pattern"
                continue

            if not matched:
                # For glob patterns, no match is normal and should not be treated as an error.
                continue

            resolved_items: list[str] = []
            for target in matched:
                if not _is_within(target, sandbox_benchmark):
                    continue
                rel_target = target.relative_to(sandbox_benchmark).as_posix()
                resolved_items.append(rel_target)
                _collect_one(key_base=f"collected_artifact::{rel_target}", target=target)

            if resolved_items:
                artifacts[f"{key_base}::matches"] = "\n".join(resolved_items[:500])
                if len(resolved_items) > 500:
                    artifacts[f"{key_base}::matches"] += "\n... (truncated)"
            continue

        target = (sandbox_benchmark / rel).resolve()
        _collect_one(key_base=key_base, target=target)


def _render_eval_command(
    *,
    command_template: str,
    candidate_dst: Path,
    sandbox_benchmark: Path,
    sandbox_root: Path,
    spec: UnifiedTaskSpec,
    runtime_python_path: str | None = None,
    repo_root_path: Path | None = None,
    benchmark_source_path: Path | None = None,
) -> str:
    python_cmd = runtime_python_path or "python"
    repo_root = repo_root_path or spec.repo_root
    benchmark_source = benchmark_source_path or spec.benchmark_dir
    quoted = {
        "python": shlex.quote(python_cmd),
        "candidate": shlex.quote(str(candidate_dst)),
        "benchmark": shlex.quote(str(sandbox_benchmark)),
        "sandbox": shlex.quote(str(sandbox_root)),
        "repo_root": shlex.quote(str(repo_root)),
        "benchmark_source": shlex.quote(str(benchmark_source)),
        "benchmark_id": shlex.quote(spec.benchmark_id),
        "python_raw": python_cmd,
        "candidate_raw": str(candidate_dst),
        "benchmark_raw": str(sandbox_benchmark),
        "sandbox_raw": str(sandbox_root),
        "repo_root_raw": str(repo_root),
        "benchmark_source_raw": str(benchmark_source),
        "benchmark_id_raw": spec.benchmark_id,
    }
    try:
        return command_template.format(**quoted)
    except KeyError as e:
        missing = str(e).strip("'")
        raise ValueError(f"Unknown placeholder in eval command: {{{missing}}}") from e


def _as_container_path(path: Path) -> str:
    return path.as_posix()


def evaluate(program_path: str, *, spec: UnifiedTaskSpec) -> Any:
    start = time.time()
    program_path_p = Path(program_path).expanduser().resolve()

    metrics: dict[str, float] = {
        "combined_score": INVALID_COMBINED_SCORE,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }
    explicit_metric_keys: set[str] = set()
    artifacts: dict[str, Any] = {
        "benchmark_id": spec.benchmark_id,
        "benchmark_dir": str(spec.benchmark_dir),
        "initial_program_rel": spec.initial_program_rel,
        "candidate_destination_rel": spec.candidate_destination_rel,
        "eval_cwd_rel": spec.eval_cwd_rel,
        "eval_command_template": spec.eval_command,
    }
    _append_agent_context(spec, artifacts)

    if not spec.benchmark_dir.is_dir():
        artifacts["error_message"] = f"benchmark dir not found: {spec.benchmark_dir}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    if not program_path_p.is_file():
        artifacts["error_message"] = f"candidate program not found: {program_path_p}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    env_timeout_s = float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "300") or "300")
    timeout_s = float(env_timeout_s)
    if spec.timeout_s is not None:
        timeout_s = max(1.0, min(timeout_s, float(spec.timeout_s)))
    timeout_budget_s = max(1.0, timeout_s)
    deadline_s = start + max(1.0, timeout_budget_s - 5.0)
    metrics["timeout_budget_s"] = float(timeout_budget_s)

    work_dir = Path(tempfile.mkdtemp(prefix=f"fe_unified_{_safe_slug(spec.benchmark_id)}_")).resolve()
    readonly_saved_modes: list[tuple[Path, int]] = []
    try:
        sandbox_benchmark = (work_dir / "benchmark").resolve()
        if spec.copy_files:
            copied_files, copied_dirs, missing_entries = _copy_selected_entries(
                benchmark_dir=spec.benchmark_dir,
                sandbox_benchmark=sandbox_benchmark,
                copy_files=spec.copy_files,
            )
            artifacts["copy_mode"] = "selected"
            if copied_files:
                artifacts["copied_files"] = "\n".join(copied_files[:1000])
            if copied_dirs:
                artifacts["copied_dirs"] = "\n".join(copied_dirs[:1000])
            if missing_entries:
                artifacts["missing_copy_entries"] = "\n".join(missing_entries[:200])
        else:
            shutil.copytree(spec.benchmark_dir, sandbox_benchmark)
            artifacts["copy_mode"] = "full_benchmark"

        candidate_dst = (sandbox_benchmark / spec.candidate_destination_rel).resolve()
        candidate_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(program_path_p, candidate_dst)
        artifacts["candidate_program"] = str(candidate_dst)

        readonly_snapshot = _snapshot_readonly(sandbox_benchmark, spec.readonly_files)
        if spec.readonly_files:
            artifacts["readonly_files"] = "\n".join(spec.readonly_files)
        readonly_saved_modes = _enforce_readonly(sandbox_benchmark, spec.readonly_files)

        # The sandbox is a *copy*. FRONTIER_ENGINEERING_ROOT (set below) points
        # at the real repo, and the candidate runs under our own uid, so it can
        # write to the source tree the sandbox was copied from -- which the
        # snapshot above does not cover. A candidate that rewrote a scoring
        # module there would score honestly this run and poison every run after
        # it, silently.
        #
        # We cannot prevent that write from inside this process (chmod is
        # reversible by the owner, and stripping the env var is not possible:
        # the scorer-side scripts depend on it). We can refuse to believe a run
        # that did it, and say so loudly enough that a human restores the tree.
        source_readonly_snapshot = _snapshot_readonly(
            spec.benchmark_dir.resolve(), spec.readonly_files
        )

        eval_cwd = (sandbox_benchmark / spec.eval_cwd_rel).resolve()
        if not _is_within(eval_cwd, sandbox_benchmark):
            artifacts["error_message"] = f"eval cwd escapes sandbox: {eval_cwd}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        if not eval_cwd.exists():
            artifacts["error_message"] = f"eval cwd does not exist: {eval_cwd}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        try:
            runtime_python_path = _resolve_runtime_python_path(
                spec.runtime_python_path,
                str(spec.repo_root),
            )
        except RuntimeError as e:
            artifacts["error_message"] = str(e)
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        env = os.environ.copy()
        env.update(spec.runtime_env)
        # Keep the run from writing bytecode caches. Those caches are now part of
        # the readonly fingerprint (see _should_ignore_fingerprint_entry), so a
        # run that generated its own would report a violation against itself.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.setdefault("FRONTIER_ENGINEERING_ROOT", str(spec.repo_root))
        env["FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR"] = str(spec.benchmark_dir)
        env["FRONTIER_EVAL_UNIFIED_BENCHMARK_DIR"] = str(sandbox_benchmark)
        env["FRONTIER_EVAL_UNIFIED_CANDIDATE_PATH"] = str(candidate_dst)
        runtime_env_dir = Path(_resolve_uv_env_dir(spec.runtime_env_name, str(spec.repo_root)))
        runtime_env_bin = runtime_env_dir / "bin"
        if runtime_env_bin.is_dir():
            env["PATH"] = f"{runtime_env_bin}{os.pathsep}{env.get('PATH', '')}"
            env["VIRTUAL_ENV"] = str(runtime_env_dir)
            artifacts["runtime_env_name"] = spec.runtime_env_name
            artifacts["runtime_env_dir"] = str(runtime_env_dir)
            default_runtime_python = runtime_env_bin / "python"
            if runtime_python_path is None and default_runtime_python.exists():
                runtime_python_path = str(default_runtime_python)

        run_cwd = eval_cwd
        if spec.runtime_isolation_mode == "docker":
            docker_executable = shutil.which("docker")
            if not docker_executable:
                artifacts["error_message"] = (
                    "task.runtime.isolation_mode=docker but docker executable is not available"
                )
                metrics["runtime_s"] = float(time.time() - start)
                return _wrap(metrics, artifacts)
            if not spec.runtime_docker_image:
                artifacts["error_message"] = (
                    "task.runtime.isolation_mode=docker requires task.runtime.docker_image"
                )
                metrics["runtime_s"] = float(time.time() - start)
                return _wrap(metrics, artifacts)

            docker_python = "python"
            if spec.runtime_python_path and not _extract_uv_env_name(spec.runtime_python_path):
                docker_python = spec.runtime_python_path

            container_workdir = Path("/workspace")
            container_repo_root = container_workdir / "repo"
            container_benchmark = container_workdir / "benchmark"
            candidate_rel = candidate_dst.relative_to(sandbox_benchmark)
            container_candidate = (container_benchmark / candidate_rel).resolve()
            eval_cwd_rel = eval_cwd.relative_to(sandbox_benchmark)
            container_eval_cwd = (container_benchmark / eval_cwd_rel).resolve()

            benchmark_source_rel: Path | None = None
            mount_external_benchmark_source = False
            if _is_within(spec.benchmark_dir, spec.repo_root):
                benchmark_source_rel = spec.benchmark_dir.resolve().relative_to(spec.repo_root.resolve())
            container_benchmark_source = (
                (container_repo_root / benchmark_source_rel).resolve()
                if benchmark_source_rel is not None
                else Path("/workspace/source_benchmark")
            )
            if benchmark_source_rel is None:
                mount_external_benchmark_source = True

            rendered_cmd = _render_eval_command(
                command_template=spec.eval_command,
                candidate_dst=Path(_as_container_path(container_candidate)),
                sandbox_benchmark=Path(_as_container_path(container_benchmark)),
                sandbox_root=Path(_as_container_path(container_workdir)),
                spec=spec,
                runtime_python_path=docker_python,
                repo_root_path=Path(_as_container_path(container_repo_root)),
                benchmark_source_path=Path(_as_container_path(container_benchmark_source)),
            )

            run_cmd = [
                docker_executable,
                "run",
                "--rm",
                "--workdir",
                _as_container_path(container_eval_cwd),
                "-v",
                f"{sandbox_benchmark}:{_as_container_path(container_benchmark)}:rw",
                "-v",
                f"{spec.repo_root}:{_as_container_path(container_repo_root)}:ro",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "512",
            ]
            if mount_external_benchmark_source:
                run_cmd += [
                    "-v",
                    f"{spec.benchmark_dir}:{_as_container_path(container_benchmark_source)}:ro",
                ]
            if spec.runtime_docker_network_disabled:
                run_cmd += ["--network", "none"]
            if spec.runtime_docker_readonly_rootfs:
                run_cmd += ["--read-only"]
            if spec.runtime_docker_user:
                run_cmd += ["--user", spec.runtime_docker_user]
            if spec.runtime_docker_tmpfs:
                run_cmd += ["--tmpfs", spec.runtime_docker_tmpfs]
            run_cmd += [
                "--entrypoint",
                spec.runtime_shell,
                spec.runtime_docker_image,
                # Not a login shell: profile scripts are attacker-writable state.
                "-c",
                rendered_cmd,
            ]
            artifacts["runtime_mode"] = "docker"
            artifacts["runtime_python_path"] = docker_python
            artifacts["runtime_docker_image"] = spec.runtime_docker_image
            artifacts["runtime_docker_executable"] = docker_executable
            artifacts["runtime_docker_network_disabled"] = bool(spec.runtime_docker_network_disabled)
            artifacts["runtime_docker_readonly_rootfs"] = bool(spec.runtime_docker_readonly_rootfs)
            if spec.runtime_docker_user:
                artifacts["runtime_docker_user"] = spec.runtime_docker_user
            if spec.runtime_docker_tmpfs:
                artifacts["runtime_docker_tmpfs"] = spec.runtime_docker_tmpfs
            env.pop("FRONTIER_ENGINEERING_ROOT", None)
            env["FRONTIER_ENGINEERING_ROOT"] = _as_container_path(container_repo_root)
            env["FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR"] = _as_container_path(container_benchmark_source)
            env["FRONTIER_EVAL_UNIFIED_BENCHMARK_DIR"] = _as_container_path(container_benchmark)
            env["FRONTIER_EVAL_UNIFIED_CANDIDATE_PATH"] = _as_container_path(container_candidate)
            run_cwd = None
        else:
            rendered_cmd = _render_eval_command(
                command_template=spec.eval_command,
                candidate_dst=candidate_dst,
                sandbox_benchmark=sandbox_benchmark,
                sandbox_root=work_dir,
                spec=spec,
                runtime_python_path=runtime_python_path,
            )
            # Not a login shell: a candidate that runs earlier in the same
            # evaluation can write ~/.bash_profile and have it sourced here.
            run_cmd = [spec.runtime_shell, "-c", rendered_cmd]
            artifacts["runtime_mode"] = "shell"

        artifacts["benchmark_cmd"] = rendered_cmd
        if spec.runtime_isolation_mode != "docker" and spec.runtime_python_path:
            artifacts["runtime_python_path"] = runtime_python_path
            if _extract_uv_env_name(spec.runtime_python_path):
                artifacts["runtime_python_path_source"] = spec.runtime_python_path
        artifacts["runtime_command"] = " ".join(shlex.quote(x) for x in run_cmd)

        try:
            proc = subprocess.run(
                run_cmd,
                cwd=str(run_cwd) if run_cwd is not None else None,
                capture_output=True,
                text=True,
                timeout=_remaining_timeout(deadline_s),
                env=env,
            )
        except FileNotFoundError as e:
            artifacts["error_message"] = f"runtime executable not found: {e}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        except subprocess.TimeoutExpired as e:
            artifacts["error_message"] = f"benchmark timeout: {e}"
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        artifacts["benchmark_stdout"] = _tail(proc.stdout)
        artifacts["benchmark_stderr"] = _tail(proc.stderr)
        artifacts["benchmark_stdout_full"] = _truncate_middle(proc.stdout)
        artifacts["benchmark_stderr_full"] = _truncate_middle(proc.stderr)
        metrics["benchmark_returncode"] = float(proc.returncode)

        loaded_metrics = False
        if spec.metrics_json_rel:
            metrics_path = (sandbox_benchmark / spec.metrics_json_rel).resolve()
            artifacts["metrics_json_path"] = str(metrics_path)
            metrics_payload = _read_json(metrics_path)
            if isinstance(metrics_payload, dict):
                loaded_metrics = True
                numeric_metrics, non_numeric_metrics = _extract_numeric_metrics(metrics_payload)
                metrics.update(numeric_metrics)
                explicit_metric_keys.update(numeric_metrics)
                if non_numeric_metrics:
                    artifacts["metrics_non_numeric"] = json.dumps(
                        non_numeric_metrics,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
            elif metrics_path.exists():
                artifacts["metrics_json_error"] = (
                    "metrics_json exists but is not valid JSON object"
                )

        if not loaded_metrics and spec.parse_stdout_json:
            parsed_stdout = _parse_last_json_dict(proc.stdout)
            if isinstance(parsed_stdout, dict):
                numeric_metrics, non_numeric_metrics = _extract_numeric_metrics(parsed_stdout)
                if numeric_metrics:
                    loaded_metrics = True
                    metrics.update(numeric_metrics)
                    explicit_metric_keys.update(numeric_metrics)
                if non_numeric_metrics:
                    artifacts["stdout_json_non_numeric"] = json.dumps(
                        non_numeric_metrics,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )

        if spec.artifacts_json_rel:
            artifacts_path = (sandbox_benchmark / spec.artifacts_json_rel).resolve()
            artifacts["artifacts_json_path"] = str(artifacts_path)
            artifacts_payload = _read_json(artifacts_path)
            if isinstance(artifacts_payload, dict):
                for key, value in artifacts_payload.items():
                    artifacts[f"user_artifact::{key}"] = value
                    # Promote common diagnostic keys so downstream algorithms do not
                    # need to know the unified `user_artifact::` naming convention.
                    if key == "error_message" and "error_message" not in artifacts:
                        artifacts["error_message"] = str(value)
                    if key == "failure_summary" and "failure_summary" not in artifacts:
                        artifacts["failure_summary"] = str(value)
            elif artifacts_path.exists():
                artifacts["artifacts_json_error"] = (
                    "artifacts_json exists but is not valid JSON object"
                )

        _collect_output_artifacts(
            sandbox_benchmark=sandbox_benchmark,
            artifact_files=spec.artifact_files,
            artifacts=artifacts,
        )

        if "valid" not in explicit_metric_keys:
            metrics["valid"] = 1.0 if proc.returncode == 0 else 0.0
        if "combined_score" not in explicit_metric_keys:
            metrics["combined_score"] = (
                1.0 if metrics.get("valid", 0.0) > 0 else INVALID_COMBINED_SCORE
            )

        if proc.returncode != 0:
            metrics["valid"] = 0.0
            metrics["combined_score"] = INVALID_COMBINED_SCORE
            if "error_message" not in artifacts:
                artifacts["error_message"] = (
                    f"evaluation command failed with return code {proc.returncode}"
                )

        if readonly_snapshot:
            violations = _check_readonly_violations(sandbox_benchmark, readonly_snapshot)
            if violations:
                metrics["readonly_violation"] = 1.0
                metrics["valid"] = 0.0
                metrics["combined_score"] = INVALID_COMBINED_SCORE
                artifacts["readonly_violations"] = "\n".join(violations[:200])
                if "error_message" not in artifacts:
                    artifacts["error_message"] = "readonly files modified by evaluation run"

        if source_readonly_snapshot:
            source_violations = _check_readonly_violations(
                spec.benchmark_dir.resolve(), source_readonly_snapshot
            )
            if source_violations:
                # Strictly worse than a sandbox violation: the sandbox is thrown
                # away, the source tree is not. Every later evaluation of this
                # task is now suspect until the tree is restored.
                metrics["readonly_violation"] = 1.0
                metrics["source_tree_violation"] = 1.0
                metrics["valid"] = 0.0
                metrics["combined_score"] = INVALID_COMBINED_SCORE
                artifacts["source_tree_violations"] = "\n".join(source_violations[:200])
                artifacts["error_message"] = (
                    "evaluation run modified the SOURCE benchmark tree at "
                    f"{spec.benchmark_dir} -- this persists across runs; restore "
                    "the tree (e.g. git checkout) before trusting any later score "
                    "for this task"
                )

        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    finally:
        _restore_modes(readonly_saved_modes)
        shutil.rmtree(work_dir, ignore_errors=True)


def _wrap(metrics: dict[str, float], artifacts: dict[str, Any]) -> Any:
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return metrics
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
