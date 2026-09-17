"""ContinuousCasting 候选完整性校验（借鉴 CVRP / TelecomBackup validator）。

在评分前以"可执行检查"强制任务约束（不只是自然语言）：
  1. EVOLVE-BLOCK 完整性：标记必须存在；标记外的代码必须与初始 baseline 逐字节一致。
  2. 禁引用：候选不得 import verification 的评测/生成模块（evaluate/generator/ref_solver），
     不得出现绝对路径，不得按实例名硬编码。
  3. 确定性：同一实例跑两次必须输出一致。
  4. candidate_env：候选子进程环境剥离 FRONTIER_*/CUTTING_EVAL_* 变量，
     封死"通过宿主环境变量定位评测基线"的侧信道。

候选允许 import `verification/simulator.py`（白盒计分器，任务有意暴露），
但不允许 import 评测/生成/参考解逻辑。纯标准库。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

EVOLVE_START = "EVOLVE-BLOCK-START"
EVOLVE_END = "EVOLVE-BLOCK-END"
PROJECT_PREFIX = "CUTTING_EVAL_"

# 禁引用 token：强 token 子串匹配即可（正常求解器几乎不会出现）。
STRONG_TOKENS = (
    "ref_solver",
    "CUTTING_EVAL_",
    "from generator",
    "import generator",
)
# "verification" 只在与评测/生成模块构成 import/路径上下文时禁止
# （候选被允许 import verification/simulator.py）。
FORBIDDEN_RE = (
    re.compile(r"verification[\\/](?:evaluate|generator|ref_solver)"),
    re.compile(r"verification\s*\.\s*(?:evaluate|generator|ref_solver)\b"),
    re.compile(r"\b(?:from|import)\s+(?:evaluate|generator|ref_solver)\b"),
)
# Windows 盘符 / POSIX 家目录绝对路径。
ABS_PATH_RE = re.compile(r"[A-Za-z]:[\\/]|/home/|/Users/")
# 按实例名硬编码，如 "instance_1": [...] 或 "gen_42_1": [...]
HARDCODE_RE = re.compile(r"[\"'](?:instance|gen)_\d+(?:_\d+)?[\"']\s*:")


def split_evolve_blocks(src: str) -> tuple[str, str, str] | None:
    start = src.find(EVOLVE_START)
    end = src.find(EVOLVE_END)
    if start == -1 or end == -1 or end <= start:
        return None
    return (
        src[:start],
        src[start + len(EVOLVE_START) : end],
        src[end + len(EVOLVE_END) :],
    )


def fixed_region(parts: tuple[str, str, str]) -> str:
    """EVOLVE-BLOCK 之外的只读部分（忽略 CRLF/LF 与结尾缺换行的无损差异）。"""
    return (parts[0] + parts[2]).replace("\r\n", "\n").rstrip("\n")


def static_check_source(src: str, baseline_src: str | None = None) -> list[str]:
    issues: list[str] = []
    parts = split_evolve_blocks(src)
    if parts is None:
        issues.append("missing EVOLVE-BLOCK-START / EVOLVE-BLOCK-END markers")
    elif baseline_src is not None:
        init_parts = split_evolve_blocks(baseline_src)
        if init_parts is not None and fixed_region(init_parts) != fixed_region(parts):
            issues.append("code outside EVOLVE-BLOCK differs from initial baseline")

    for token in STRONG_TOKENS:
        if token in src:
            issues.append(f"candidate references forbidden token {token!r}")
    for pat in FORBIDDEN_RE:
        if pat.search(src):
            issues.append("candidate references forbidden evaluation/generation/ref module")

    if ABS_PATH_RE.search(src):
        issues.append("candidate contains an absolute filesystem path")
    if HARDCODE_RE.search(src):
        issues.append("candidate hardcodes per-instance schedules by name")

    return issues


def check_candidate(
    solver_path: Path | str, baseline_path: Path | str | None = None
) -> list[str]:
    solver_path = Path(solver_path)
    try:
        src = solver_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return [f"cannot read candidate source: {exc}"]

    baseline_src = None
    if baseline_path is not None:
        try:
            baseline_src = Path(baseline_path).read_text(
                encoding="utf-8", errors="replace"
            )
        except Exception:
            baseline_src = None
    return static_check_source(src, baseline_src)


def candidate_env() -> dict[str, str]:
    """候选子进程环境：剥离宿主路径与评测相关变量。"""
    env = os.environ.copy()
    for key in list(env):
        upper = key.upper()
        if upper.startswith("FRONTIER") or upper.startswith(PROJECT_PREFIX):
            del env[key]
    return env


def check_determinism(
    python: str,
    solver_path: Path | str,
    inst_path: Path | str,
    timeout: float,
) -> tuple[bool, str]:
    """同一实例跑两次，输出必须一致。"""
    solver_path = Path(solver_path)
    inst_path = Path(inst_path)
    outputs: list[Any] = []
    for _ in range(2):
        try:
            proc = subprocess.run(
                [python, str(solver_path), str(inst_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(solver_path.parent),
                env=candidate_env(),
            )
        except subprocess.TimeoutExpired:
            return False, "timeout during determinism check"
        except Exception as exc:
            return False, f"error during determinism check: {exc}"
        if proc.returncode != 0:
            return False, f"candidate exited with code {proc.returncode}"
        try:
            outputs.append(json.loads(proc.stdout))
        except Exception as exc:
            return False, f"cannot parse determinism output: {exc}"
    if outputs[0] != outputs[1]:
        return False, "candidate is not deterministic (output differs across two runs)"
    return True, ""
