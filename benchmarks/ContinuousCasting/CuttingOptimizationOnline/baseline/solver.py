#!/usr/bin/env python3
"""在线切割 baseline 求解器（朴素：恒定切目标值，无视异常）。

用法：python solver.py <state.json>
读取一个状态 JSON（决策点），向 stdout 打印 {"piece_length": L}（L ∈ [min_basic, max_basic]）。
本 solver 由评估器在时间线上每个决策点调用一次；state 只含"已揭示"异常。

只允许修改 EVOLVE-BLOCK 区域内的代码；接口契约（main/JSON/JSON）必须保留。

基线是"恒定切目标值、不在意报废段"：从不根据 visible_defects 调整长度。
在会出现异常的实例上，它常把报废段切进整块成品里（或切出超/欠目标），
因此明显弱于"看到异常勤快避让"的 agent，更弱于全知参考解。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def decide(state: dict) -> float:
    """给定一个决策点状态，返回下一刀切段长度。"""
    # EVOLVE-BLOCK-START
    # 朴素策略：恒定切到用户目标值，并夹到 [min_basic, max_basic]。
    # 完全不看 state["visible_defects"]（不理会报废段），因此容易踩雷。
    t = float(state.get("target", 9.5))
    lo = float(state["limits"]["min_basic"])
    hi = float(state["limits"]["max_basic"])
    total = float(state["total_length"])
    cut_pos = float(state["cut_pos"])
    remaining = total - cut_pos
    # 若剩余可直接作为最后一段，则切剩余（保证合法尾段）。
    if remaining <= hi:
        return max(lo, remaining)
    cand = max(lo, min(hi, t))
    # 避免留下 (0, lo) 的非法尾段：缩短当前块，让余段恰好为 lo。
    if 0 < remaining - cand < lo:
        cand = remaining - lo
        if cand < lo:
            cand = remaining  # 退化为整段（此时 remaining 应 >= lo）
    return max(lo, min(hi, cand))
    # EVOLVE-BLOCK-END


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python solver.py <state.json>", file=sys.stderr)
        return 2
    state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps({"piece_length": decide(state)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
