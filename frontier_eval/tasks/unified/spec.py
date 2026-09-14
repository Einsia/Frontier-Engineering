from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from omegaconf import DictConfig, OmegaConf


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, DictConfig):
        plain = OmegaConf.to_container(value, resolve=True)
        if isinstance(plain, dict):
            return dict(plain)
        return {}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _as_str_list(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    raise TypeError(f"`task.{field_name}` must be a list or string, got {type(value)}")


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _read_list_file(path: Path) -> list[str]:
    text = _read_text(path)
    if text is None:
        return []
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        out.append(line)
    return out


def _read_scalar_file(path: Path) -> str | None:
    lines = _read_list_file(path)
    if not lines:
        return None
    return lines[0]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _safe_relpath(value: str, *, field_name: str, allow_dot: bool) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"`task.{field_name}` is empty")

    path = Path(text)
    if path.is_absolute():
        raise ValueError(f"`task.{field_name}` must be a relative path: {text}")

    parts = [part for part in path.parts if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError(f"`task.{field_name}` cannot contain '..': {text}")

    if not parts:
        if allow_dot:
            return "."
        raise ValueError(f"`task.{field_name}` cannot be '.'")
    return Path(*parts).as_posix()


def _resolve_benchmark_dir(*, repo_root: Path, cfg: Mapping[str, Any]) -> tuple[Path, str]:
    benchmark_raw = str(cfg.get("benchmark") or os.environ.get("FRONTIER_EVAL_UNIFIED_BENCHMARK", "")).strip()
    if not benchmark_raw:
        raise ValueError(
            "UnifiedTask requires `task.benchmark` "
            "(e.g. `task.benchmark=KernelEngineering/TriMul`)."
        )

    benchmark_root = str(cfg.get("benchmark_root") or "benchmarks").strip() or "benchmarks"
    benchmark_path = Path(benchmark_raw).expanduser()

    if benchmark_path.is_absolute():
        benchmark_dir = benchmark_path.resolve()
    else:
        under_benchmarks = (repo_root / benchmark_root / benchmark_path).resolve()
        if under_benchmarks.exists():
            benchmark_dir = under_benchmarks
        else:
            under_repo = (repo_root / benchmark_path).resolve()
            benchmark_dir = under_repo if under_repo.exists() else under_benchmarks

    benchmark_root_abs = (repo_root / benchmark_root).resolve()
    try:
        benchmark_id = benchmark_dir.relative_to(benchmark_root_abs).as_posix()
    except Exception:
        benchmark_id = benchmark_dir.name
    return benchmark_dir, benchmark_id


def _resolve_metadata_path(*, benchmark_dir: Path, metadata_dir: str, file_name: str) -> Path:
    file_name = str(file_name or "").strip()
    if not file_name:
        raise ValueError("metadata file name is empty")

    raw = Path(file_name).expanduser()
    if raw.is_absolute():
        return raw.resolve()

    if metadata_dir:
        return (benchmark_dir / metadata_dir / raw).resolve()
    return (benchmark_dir / raw).resolve()


@dataclass(frozen=True)
class UnifiedTaskSpec:
    repo_root: Path
    benchmark_dir: Path
    benchmark_id: str
    initial_program_rel: str
    candidate_destination_rel: str
    eval_command: str
    eval_cwd_rel: str
    agent_files: tuple[str, ...]
    copy_files: tuple[str, ...]
    readonly_files: tuple[str, ...]
    artifact_files: tuple[str, ...]
    constraints_text: str | None
    constraints_path: Path | None
    metrics_json_rel: str | None
    artifacts_json_rel: str | None
    parse_stdout_json: bool
    timeout_s: float | None
    runtime_python_path: str | None
    runtime_env_name: str
    runtime_isolation_mode: str
    runtime_docker_image: str | None
    runtime_docker_network_disabled: bool
    runtime_docker_readonly_rootfs: bool
    runtime_docker_user: str | None
    runtime_docker_tmpfs: str | None
    runtime_shell: str
    runtime_env: dict[str, str]

    @property
    def initial_program_path(self) -> Path:
        return (self.benchmark_dir / self.initial_program_rel).resolve()


def load_unified_task_spec(*, task_cfg: Any, repo_root: Path) -> UnifiedTaskSpec:
    cfg = _as_dict(task_cfg)
    benchmark_dir, benchmark_id = _resolve_benchmark_dir(repo_root=repo_root, cfg=cfg)

    metadata_dir_raw = str(cfg.get("metadata_dir", "frontier_eval") or "").strip()
    metadata_dir = ""
    if metadata_dir_raw:
        metadata_dir = _safe_relpath(
            metadata_dir_raw,
            field_name="metadata_dir",
            allow_dot=True,
        )
        if metadata_dir == ".":
            metadata_dir = ""

    initial_program = str(cfg.get("initial_program") or "").strip()
    if not initial_program:
        initial_program_file = str(cfg.get("initial_program_file") or "initial_program.txt")
        path = _resolve_metadata_path(
            benchmark_dir=benchmark_dir,
            metadata_dir=metadata_dir,
            file_name=initial_program_file,
        )
        initial_program = str(_read_scalar_file(path) or "").strip()
    if not initial_program:
        raise ValueError(
            "Missing initial program. Set `task.initial_program` or create "
            "`<benchmark>/<metadata_dir>/initial_program.txt`."
        )
    initial_program_rel = _safe_relpath(initial_program, field_name="initial_program", allow_dot=False)

    candidate_destination = str(cfg.get("candidate_destination") or "").strip()
    if not candidate_destination:
        candidate_destination_file = str(cfg.get("candidate_destination_file") or "").strip()
        if candidate_destination_file:
            path = _resolve_metadata_path(
                benchmark_dir=benchmark_dir,
                metadata_dir=metadata_dir,
                file_name=candidate_destination_file,
            )
            candidate_destination = str(_read_scalar_file(path) or "").strip()
    candidate_destination_rel = (
        _safe_relpath(
            candidate_destination,
            field_name="candidate_destination",
            allow_dot=False,
        )
        if candidate_destination
        else initial_program_rel
    )

    eval_command = str(cfg.get("eval_command") or "").strip()
    if not eval_command:
        eval_command_file = str(cfg.get("eval_command_file") or "eval_command.txt")
        path = _resolve_metadata_path(
            benchmark_dir=benchmark_dir,
            metadata_dir=metadata_dir,
            file_name=eval_command_file,
        )
        text = _read_text(path)
        eval_command = str(text or "").strip()
    if not eval_command:
        raise ValueError(
            "Missing evaluation command. Set `task.eval_command` or create "
            "`<benchmark>/<metadata_dir>/eval_command.txt`."
        )

    eval_cwd = str(cfg.get("eval_cwd") or "").strip()
    if not eval_cwd:
        eval_cwd_file = str(cfg.get("eval_cwd_file") or "").strip()
        if eval_cwd_file:
            path = _resolve_metadata_path(
                benchmark_dir=benchmark_dir,
                metadata_dir=metadata_dir,
                file_name=eval_cwd_file,
            )
            eval_cwd = str(_read_scalar_file(path) or "").strip()
    eval_cwd_rel = _safe_relpath(eval_cwd or ".", field_name="eval_cwd", allow_dot=True)

    inline_agent_files = _as_str_list(cfg.get("agent_files"), field_name="agent_files")
    agent_files_file = str(cfg.get("agent_files_file") or "agent_files.txt")
    agent_files_path = _resolve_metadata_path(
        benchmark_dir=benchmark_dir,
        metadata_dir=metadata_dir,
        file_name=agent_files_file,
    )
    file_agent_files = _read_list_file(agent_files_path)
    agent_files = tuple(
        _safe_relpath(item, field_name="agent_files", allow_dot=False)
        for item in _dedupe(inline_agent_files + file_agent_files)
    )

    inline_copy_files = _as_str_list(cfg.get("copy_files"), field_name="copy_files")
    copy_files_file = str(cfg.get("copy_files_file") or "copy_files.txt")
    copy_files_path = _resolve_metadata_path(
        benchmark_dir=benchmark_dir,
        metadata_dir=metadata_dir,
        file_name=copy_files_file,
    )
    file_copy_files = _read_list_file(copy_files_path)
    copy_files = tuple(
        _safe_relpath(item, field_name="copy_files", allow_dot=True)
        for item in _dedupe(inline_copy_files + file_copy_files)
    )

    inline_readonly_files = _as_str_list(cfg.get("readonly_files"), field_name="readonly_files")
    readonly_files_file = str(cfg.get("readonly_files_file") or "readonly_files.txt")
    readonly_files_path = _resolve_metadata_path(
        benchmark_dir=benchmark_dir,
        metadata_dir=metadata_dir,
        file_name=readonly_files_file,
    )
    file_readonly_files = _read_list_file(readonly_files_path)
    readonly_files = tuple(
        _safe_relpath(item, field_name="readonly_files", allow_dot=True)
        for item in _dedupe(inline_readonly_files + file_readonly_files)
    )

    inline_artifact_files = _as_str_list(cfg.get("artifact_files"), field_name="artifact_files")
    artifact_files_file = str(cfg.get("artifact_files_file") or "artifact_files.txt")
    artifact_files_path = _resolve_metadata_path(
        benchmark_dir=benchmark_dir,
        metadata_dir=metadata_dir,
        file_name=artifact_files_file,
    )
    file_artifact_files = _read_list_file(artifact_files_path)
    artifact_files = tuple(
        _safe_relpath(item, field_name="artifact_files", allow_dot=False)
        for item in _dedupe(inline_artifact_files + file_artifact_files)
    )

    constraints_text = str(cfg.get("constraints_text") or "").strip() or None
    constraints_path: Path | None = None
    if constraints_text is None:
        constraints_file = str(cfg.get("constraints_file") or "constraints.txt")
        path = _resolve_metadata_path(
            benchmark_dir=benchmark_dir,
            metadata_dir=metadata_dir,
            file_name=constraints_file,
        )
        text = _read_text(path)
        if text is not None:
            constraints_text = text.strip() or None
            constraints_path = path

    metrics_json_raw = cfg.get("metrics_json", "metrics.json")
    if metrics_json_raw is None or str(metrics_json_raw).strip() == "":
        metrics_json_rel = None
    else:
        metrics_json_rel = _safe_relpath(
            str(metrics_json_raw),
            field_name="metrics_json",
            allow_dot=False,
        )

    artifacts_json_raw = cfg.get("artifacts_json", "artifacts.json")
    if artifacts_json_raw is None or str(artifacts_json_raw).strip() == "":
        artifacts_json_rel = None
    else:
        artifacts_json_rel = _safe_relpath(
            str(artifacts_json_raw),
            field_name="artifacts_json",
            allow_dot=False,
        )

    timeout_raw = cfg.get("timeout_s", None)
    timeout_s: float | None = None
    if timeout_raw is not None and str(timeout_raw).strip() != "":
        timeout_v = float(timeout_raw)
        timeout_s = timeout_v if timeout_v > 0 else None

    runtime_cfg = _as_dict(cfg.get("runtime"))
    runtime_python_path = (
        str(runtime_cfg.get("python_path") or os.environ.get("FRONTIER_EVAL_UNIFIED_PYTHON", "")).strip() or None
    )
    runtime_env_name = (
        str(
            runtime_cfg.get("env_name")
            or os.environ.get("FRONTIER_EVAL_UNIFIED_RUNTIME_ENV", "frontier-eval-driver")
        ).strip()
        or "frontier-eval-driver"
    )
    runtime_isolation_mode = str(runtime_cfg.get("isolation_mode") or "process").strip().lower() or "process"
    if runtime_isolation_mode not in {"process", "docker"}:
        raise ValueError(
            f"`task.runtime.isolation_mode` must be 'process' or 'docker', got {runtime_isolation_mode!r}"
        )
    runtime_docker_image = str(runtime_cfg.get("docker_image") or "").strip() or None
    runtime_docker_network_disabled = _as_bool(runtime_cfg.get("docker_network_disabled"), default=True)
    runtime_docker_readonly_rootfs = _as_bool(runtime_cfg.get("docker_readonly_rootfs"), default=True)
    runtime_docker_user = str(runtime_cfg.get("docker_user") or "").strip() or None
    runtime_docker_tmpfs = str(runtime_cfg.get("docker_tmpfs") or "").strip() or None
    runtime_shell = str(runtime_cfg.get("shell") or "bash").strip() or "bash"

    runtime_env_raw = runtime_cfg.get("env") or {}
    if not isinstance(runtime_env_raw, dict):
        raise TypeError(f"`task.runtime.env` must be a mapping, got {type(runtime_env_raw)}")
    runtime_env = {str(k): str(v) for k, v in runtime_env_raw.items()}

    # Default False: parsing the combined_score from a candidate program's
    # stdout is a spoofing channel (see conf/task/unified.yaml). The value only
    # comes back into play when a task explicitly opts in.
    parse_stdout_json = _as_bool(cfg.get("parse_stdout_json"), default=False)

    return UnifiedTaskSpec(
        repo_root=repo_root.resolve(),
        benchmark_dir=benchmark_dir.resolve(),
        benchmark_id=benchmark_id,
        initial_program_rel=initial_program_rel,
        candidate_destination_rel=candidate_destination_rel,
        eval_command=eval_command,
        eval_cwd_rel=eval_cwd_rel,
        agent_files=agent_files,
        copy_files=copy_files,
        readonly_files=readonly_files,
        artifact_files=artifact_files,
        constraints_text=constraints_text,
        constraints_path=constraints_path,
        metrics_json_rel=metrics_json_rel,
        artifacts_json_rel=artifacts_json_rel,
        parse_stdout_json=parse_stdout_json,
        timeout_s=timeout_s,
        runtime_python_path=runtime_python_path,
        runtime_env_name=runtime_env_name,
        runtime_isolation_mode=runtime_isolation_mode,
        runtime_docker_image=runtime_docker_image,
        runtime_docker_network_disabled=runtime_docker_network_disabled,
        runtime_docker_readonly_rootfs=runtime_docker_readonly_rootfs,
        runtime_docker_user=runtime_docker_user,
        runtime_docker_tmpfs=runtime_docker_tmpfs,
        runtime_shell=runtime_shell,
        runtime_env=runtime_env,
    )
