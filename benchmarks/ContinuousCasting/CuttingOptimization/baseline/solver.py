#!/usr/bin/env python3
"""连铸切割 baseline 求解器（朴素基线：每个干净坯段均匀等分）。

用法：python solver.py <instance.json>
输出：stdout 打印 {"cuts": [c1, c2, ...]}，cuts 为切段长度列表，之和 = total_length。

只允许修改 EVOLVE-BLOCK 区域内的代码；接口契约（main/stdin-json/stdout-json）必须保留。

基线取"均匀等分"（朴素、不针对目标窗口）：每段长度取 [min_basic, max_basic] 内的均匀值，
但完全不考虑用户目标值 T，因此产生大量超出 target_max 的报废（或落在 target_min 下方
的偏短块）。参考解（按目标窗口做一维划分 DP）能显著超越它，故基线是一个"正常且被明显超越"的起点。
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def clean_segments(inst: dict) -> list[list[float]]:
    """干净坯段列表 [[start, length], ...]（零废段之外的可切材料）。"""
    total = float(inst["billet"]["total_length"])
    defects = [list((a, b)) for a, b in (inst.get("defects") or [])]
    segs: list[list[float]] = []
    prev = 0.0
    for a, b in defects:
        segs.append([prev, a - prev])
        prev = b
    segs.append([prev, total - prev])
    return [s for s in segs if s[1] > 1e-9]


def solve(inst: dict) -> list[float]:
    """返回完整钢坯的切段长度列表（含零废段小块）。"""
    # EVOLVE-BLOCK-START
    def partition(length: float) -> list[float]:
        """把一段干净坯 length 等分成若干块，每块在 [min_basic, max_basic]。"""
        a = float(inst["limits"]["min_basic"])
        b = float(inst["limits"]["max_basic"])
        n = max(1, math.ceil(length / b))
        while n > 1 and length / n < a:
            n -= 1
        while length / n > b:
            n += 1
        base = length / n
        pieces = [base] * n
        pieces[-1] = length - base * (n - 1)
        return [round(p, 4) for p in pieces]

    segs = clean_segments(inst)
    defects = sorted((list((a, b)) for a, b in (inst.get("defects") or [])), key=lambda x: x[0])
    cuts: list[float] = []
    for i, (_start, length) in enumerate(segs):
        cuts.extend(partition(length))
        if i < len(defects):
            a, b = defects[i]
            cuts.append(round(b - a, 4))  # 零废段强制切出
    return cuts
    # EVOLVE-BLOCK-END


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python solver.py <instance.json>", file=sys.stderr)
        return 2
    inst_path = Path(sys.argv[1])
    inst = json.loads(inst_path.read_text(encoding="utf-8"))
    cuts = solve(inst)
    print(json.dumps({"cuts": cuts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
