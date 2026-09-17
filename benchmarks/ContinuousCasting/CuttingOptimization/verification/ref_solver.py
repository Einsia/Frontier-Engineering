"""连铸切割参考解（一维划分 DP），纯 Python 标准库。

思路：零废段把钢坯 [0, S] 分成若干"干净坯段"；每段独立做切割优化。
每段用一个网格化 DP：状态 = 已覆盖长度（以 GRID 为步长），
转移 = 选一块长度 c 属于 [min_basic, max_basic]，代价 = 该块的
 scrap + lambda*penalty。段内最小总代价即最优。

注意：实例中的所有长度（S、零废段位置、scrap_len、min/max_basic）都取
0.1 米的多倍，而 GRID=0.02，故 all 长度都是 GRID 的多倍 → DP 无舍入误差，
参考解切段长度之和恰好等于 S（可直接通过 sum≈S 校验）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 保证同目录 import

from simulator import (  # noqa: E402
    MAX_BASIC,
    MIN_BASIC,
    TARGET_PENALTY_WEIGHT,
    clean_segments,
    piece_penalty,
    piece_scrap,
)

GRID = 0.02


def _build_cost_table(inst: dict[str, Any]) -> tuple[int, int, list[float]]:
    """返回 (min_steps, max_steps, costs)；costs[s-min_steps] = 切一块 s*GRID 的代价。"""
    min_steps = int(round(MIN_BASIC / GRID))
    max_steps = int(round(MAX_BASIC / GRID))
    costs = []
    for s in range(min_steps, max_steps + 1):
        c = s * GRID
        costs.append(piece_scrap(c, inst) + TARGET_PENALTY_WEIGHT * piece_penalty(c, inst))
    return min_steps, max_steps, costs


def _optimize_segment(inst: dict[str, Any], length: float) -> list[float]:
    """对单个干净坯段做最优切割，返回该段的切段长度列表（之和 = length）。"""
    n = int(round(length / GRID))
    if n <= 0:
        return []
    min_steps, max_steps, costs = _build_cost_table(inst)
    INF = float("inf")
    f = [INF] * (n + 1)
    bp = [-1] * (n + 1)
    f[0] = 0.0
    for pos in range(min_steps, n + 1):
        best = INF
        best_s = -1
        hi = min(max_steps, pos)
        for s in range(min_steps, hi + 1):
            prev = f[pos - s]
            if prev >= INF:
                continue
            val = prev + costs[s - min_steps]
            if val < best:
                best = val
                best_s = s
        f[pos] = best
        bp[pos] = best_s

    if f[n] >= INF:
        return _fallback(inst, length)

    pieces: list[float] = []
    pos = n
    while pos > 0:
        s = bp[pos]
        pieces.append(round(s * GRID, 4))
        pos -= s
    pieces.reverse()
    return pieces


def _fallback(inst: dict[str, Any], length: float) -> list[float]:
    """极少数非网格情况：尽量切成 [min_basic, max_basic] 的均匀段。"""
    k = int(length // MAX_BASIC)
    if k == 0:
        return [length]
    base = length / (k + 1)
    if base < MIN_BASIC:
        return [length]
    return [round(base, 4)] * (k + 1)


def solve(inst: dict[str, Any]) -> dict[str, Any]:
    """返回 {'cuts': [...]}：完整钢坯的最优切段（含零废段小块）。"""
    segs = clean_segments(inst)
    defects = sorted((list((a, b)) for a, b in inst["defects"] or []), key=lambda x: x[0])
    cuts: list[float] = []
    for i, (_start, length) in enumerate(segs):
        cuts.extend(_optimize_segment(inst, length))
        if i < len(defects):
            a, b = defects[i]
            cuts.append(round(b - a, 4))  # 零废段强制切出
    return {"cuts": cuts}


def total_scrap(inst: dict[str, Any], cuts: list[float]) -> float:
    """给定切段方案，返回总报废长度（用于实例验收/对比）。"""
    from simulator import score

    ok, m = score(inst, cuts)
    return m["scrap"] if ok else float("inf")
