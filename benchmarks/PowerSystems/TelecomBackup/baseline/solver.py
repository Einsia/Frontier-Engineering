#!/usr/bin/env python3
"""区域备电 baseline 求解器（朴素基线：全程开启，不做时序调度）。

用法：python baseline/solver.py <instance.json>
输出：stdout 打印 {"on": [[[a,b),...], ...]}，on[k] 为电源 k 的开启时隙区间列表
（0-index，半开区间；[[0, horizon]] = 全程开启，[] = 全程关闭）。

只允许修改 EVOLVE-BLOCK 区域内的代码；接口契约（main/stdin-json/stdout-json）必须保留。

基线取"全程开启"（朴素、无调度）：覆盖最高但电池并行耗尽。校准后的实例保证
"错峰调度"（多路轮流休息）能显著超越它（参考启发式 +54%），因此基线是一个
"正常且可被明显超越"的起点。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def solve(inst: dict) -> list[list[list[int]]]:
    """返回 on_intervals 列表（每电源的开启时隙区间）。"""
    # EVOLVE-BLOCK-START
    # 朴素策略：所有电源全程开启（不调度）。这是合法的基线解——
    # 覆盖最高但电池并行耗尽；通过"时序开关调度"（错峰/轮换供电，
    # 让电池错峰放电、利用覆盖冗余）可以显著延长备电时长。
    k = len(inst["groups"])
    horizon = int(inst["horizon"])
    return [[[0, horizon]] for _ in range(k)]
    # EVOLVE-BLOCK-END


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python solver.py <instance.json>", file=sys.stderr)
        return 2
    inst_path = Path(sys.argv[1])
    inst = json.loads(inst_path.read_text(encoding="utf-8"))
    on = solve(inst)
    print(json.dumps({"on": on}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
