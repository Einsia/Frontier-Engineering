"""在线切割全知参考解（clairvoyant，看到全部报废表）。

静态一维划分 DP（网格化，纯标准库）：
- 流坐标 [0,S]，网格 GRID；每块长度 ∈ [min_basic, max_basic]。
- 一块若与任一报废段区间重叠 -> 整块报废（cost = 块长，无贴合度惩罚）；
  否则按干净块规则（<min_process 整损 / 超 target_max 超损 / 贴合度惩罚）。
- 最小化 total_cost = scrap + lambda*penalty（lambda 极小，保证字典序）。

注意：本参考解看到全部异常，因此它是在线 agent 的**理论上限**（天花板）。
在线 agent（限视 reveal_lead）无法达到它——这正是"在线比离线难"的体现。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from simulator import score  # noqa: E402  # 复用评分/校验

GRID = 0.02
LAMBDA = 1e-4
OVERLAP_TOL = 1e-6


def _limits(inst: dict[str, Any]):
    lim = inst.get("limits", {})
    return (float(lim.get("min_basic", 4.8)), float(lim.get("max_basic", 12.6)),
            float(lim.get("min_process", 8.0)))


def _piece_overlap(x0: float, x1: float, defects: list[list[float]]) -> bool:
    for xa, xb in defects:
        if x1 > xa + OVERLAP_TOL and x0 < xb - OVERLAP_TOL:
            return True
    return False


def _cost(inst: dict[str, Any], x0: float, c: float, defects: list[list[float]]) -> float:
    if _piece_overlap(x0, x0 + c, defects):
        return c  # 污染块，整块报废（无贴合度惩罚）
    t = float(inst["customer"]["target"])
    t_max = float(inst["customer"]["target_max"])
    lim_min_proc = _limits(inst)[2]
    if c < lim_min_proc:
        return c
    scrap = max(0.0, c - t_max)
    penalty = abs(min(c, t_max) - t)
    return scrap + LAMBDA * penalty


def solve(inst: dict[str, Any]) -> dict[str, Any]:
    """返回 {'cuts': [...]}：全知最优切段。"""
    import math

    S = float(inst["cast"]["total_length"])
    defects = [list((a, b)) for a, b in inst.get("defects", []) or []]
    min_basic, max_basic, _ = _limits(inst)
    n = max(1, int(round(S / GRID)))
    min_steps = int(round(min_basic / GRID))
    max_steps = int(round(max_basic / GRID))

    INF = float("inf")
    f = [INF] * (n + 1)
    bp = [-1] * (n + 1)
    f[0] = 0.0
    for pos in range(min_steps, n + 1):
        best = INF
        best_s = -1
        hi = min(max_steps, pos)
        for s in range(min_steps, hi + 1):
            prev = pos - s
            if f[prev] >= INF:
                continue
            val = f[prev] + _cost(inst, prev * GRID, s * GRID, defects)
            if val < best:
                best = val
                best_s = s
        f[pos] = best
        bp[pos] = best_s

    if f[n] >= INF:
        # 兜底：均匀等分（保证产出合法切段）
        k = max(1, math.ceil(S / max_basic))
        base = S / k
        cuts = [round(base, 4)] * k
        return {"cuts": cuts}

    cuts: list[float] = []
    pos = n
    while pos > 0:
        s = bp[pos]
        cuts.append(round(s * GRID, 4))
        pos -= s
    cuts.reverse()
    # 消除浮点累计误差，使求和精确等于 S
    drift = S - sum(cuts)
    cuts[-1] = round(cuts[-1] + drift, 4)
    return {"cuts": cuts}


def best_util(inst: dict[str, Any]) -> float:
    """全知参考解的材料利用率。"""
    cuts = solve(inst)["cuts"]
    ok, m = score(inst, cuts)
    return m.get("util", 0.0) if ok else 0.0
