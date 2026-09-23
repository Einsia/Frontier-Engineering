#!/usr/bin/env python3
"""参考求解器：轮流休息一路的错峰调度（"好解"参考，供 agent 对比/超越）。

思路：全程开启会让所有电池并行耗尽；"轮流休息一路"（其余保持负载分散）
能让被休息的电源以低静默功耗保电，从而延长总备电时长。对 R（休息窗口）
做小范围搜索取最优。

用法：python verification/ref_solver.py <instance.json>
输出：stdout 打印 {"on": [[[a,b),...], ...]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))
from simulator import simulate  # noqa: E402


def solve(inst: dict) -> list[list[list[int]]]:
    horizon = int(inst["horizon"])
    k = len(inst["groups"])
    best_on = [[[0, horizon]] for _ in range(k)]
    best_s = simulate(inst, best_on)
    for n_rest in (1, 2, 3):
        for r in (2, 4, 6, 8, 12, 16):
            on = [[] for _ in range(k)]
            slot = seg = 0
            while slot < horizon:
                for i in range(k):
                    if (seg + i) % k >= n_rest:
                        on[i].append([slot, min(slot + r, horizon)])
                slot += r
                seg += 1
            s = simulate(inst, on)
            if s > best_s:
                best_s, best_on = s, on
    return best_on


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python ref_solver.py <instance.json>", file=sys.stderr)
        return 2
    inst_path = Path(sys.argv[1])
    inst = json.loads(inst_path.read_text(encoding="utf-8"))
    print(json.dumps({"on": solve(inst)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
