"""在线切割候选完整性校验（静态检查 + 环境剥离，借鉴离线/CVRP 惯例）。

评分前以可执行检查强制约束：
  1. EVOLVE-BLOCK 完整性 + 标记外代码与初始 baseline 逐字节一致；
  2. 禁引用评测/生成/参考解模块（evaluate/generator/ref_solver）、绝对路径、按实例名硬编码；
  3. candidate_env：候选子进程剥离 FRONTIER_*/ONLINE_CUT_EVAL_* 变量，封宿主侧信道。
  4. 确定性探针（闭环跑两遍）在 evaluate.py 中执行。

候选允许 import verification/simulator.py（白盒计分器），但禁止评测/生成/参考解逻辑。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

EVOLVE_START = "EVOLVE-BLOCK-START"
EVOLVE_END = "EVOLVE-BLOCK-END"
PROJECT_PREFIX = "ONLINE_CUT_EVAL_"

STRONG_TOKENS = (
    "ref_solver",
    "ONLINE_CUT_EVAL_",
    "from generator",
    "import generator",
    "anomaly_seed",
)
FORBIDDEN_RE = (
    re.compile(r"verification[\\/](?:evaluate|generator|ref_solver)"),
    re.compile(r"verification\s*\.\s*(?:evaluate|generator|ref_solver)\b"),
    re.compile(r"\b(?:from|import)\s+(?:evaluate|generator|ref_solver)\b"),
)
ABS_PATH_RE = re.compile(r"[A-Za-z]:[\\/]|/home/|/Users/")
HARDCODE_RE = re.compile(r"[\"'](?:instance|gen)_\d+(?:_\d+)?[\"']\s*:")


def split_evolve_blocks(src: str) -> tuple[str, str, str] | None:
    start = src.find(EVOLVE_START)
    end = src.find(EVOLVE_END)
    if start == -1 or end == -1 or end <= start:
        return None
    return (src[:start], src[start + len(EVOLVE_START):end], src[end + len(EVOLVE_END):])


def fixed_region(parts: tuple[str, str, str]) -> str:
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


def check_candidate(solver_path: Path | str, baseline_path: Path | str | None = None) -> list[str]:
    solver_path = Path(solver_path)
    try:
        src = solver_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return [f"cannot read candidate source: {exc}"]
    baseline_src = None
    if baseline_path is not None:
        try:
            baseline_src = Path(baseline_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            baseline_src = None
    return static_check_source(src, baseline_src)


def candidate_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        upper = key.upper()
        if upper.startswith("FRONTIER") or upper.startswith(PROJECT_PREFIX):
            del env[key]
    return env
