"""连铸切割实例生成器：seed 固定，生成可复现的一维切割实例（JSON）。

参数语义：
- 钢坯是一维线段 [0, S]（S = total_length）。
- 结晶器异常在坯内产生若干"零废段"（每段长 scrap_len=0.8m），必须被切出（报废）。
- 用户目标值 T、范围 [target_min, target_max]；工艺参数与长度窗口见 LIMITS。
- 难度由 total_length、零废段数量、目标窗口宽度共同决定。

零废段位置限制：相邻零废段、零废段与线段两端之间必须留出 >= min_basic 的干净坯段，
否则该段 < min_basic 无法成一块（不可行）。生成时强制该约束。
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # 保证同目录 import

# 长度窗口（与 simulator.py 保持一致）
MIN_BASIC = 4.8     # 能运走的最小长度
MAX_BASIC = 12.6    # 能运走的最大长度
MIN_PROCESS = 8.0   # 下道工序可接受的最小长度
MAX_PROCESS = 11.6  # 下道工序可接受的最大长度

PROCESS = {
    "speed": 1.0,       # 拉坯速度 (m/min)
    "cut_time": 3,      # 切一块耗时 (min)
    "return_time": 1,   # 切完回工作起点 (min)
    "buffer_len": 60.0, # 结晶器中心到切割机工作起点 (m)
    "scrap_len": 0.8,   # 结晶器异常产生的零废段长度 (m)
}


def _clamp_times(T: float) -> tuple[float, float]:
    return T - 0.5, T + 0.5


def _target_options(rng: random.Random) -> tuple[float, float]:
    """从赛题提及的目标值集合里挑一个（8.5 / 9.5 / 11.1）。"""
    return float(rng.choice([8.5, 9.5, 11.1]))


def generate(seed: int, difficulty: str = "medium") -> dict[str, Any]:
    """按种子生成一个切割实例。

    difficulty: "easy" | "medium" | "hard"。easy 给短坯+零废段少，
    hard 给长坯+零废段多（且窗口更紧）。
    """
    rng = random.Random(seed)

    if difficulty == "easy":
        s_lo, s_hi = 24.0, 70.0
        n_def_lo, n_def_hi = 0, 1
    elif difficulty == "hard":
        s_lo, s_hi = 100.0, 150.0
        n_def_lo, n_def_hi = 3, 6
    else:  # medium
        s_lo, s_hi = 60.0, 110.0
        n_def_lo, n_def_hi = 1, 3

    S = round(rng.uniform(s_lo, s_hi), 1)
    T = _target_options(rng)
    t_min, t_max = _clamp_times(T)

    # 生成零废段位置：彼此、与两端之间都留出 >= MIN_BASIC 干净坯。
    n_def = rng.randint(n_def_lo, n_def_hi)
    scrap_len = PROCESS["scrap_len"]
    defects: list[list[float]] = []
    # 可用的"槽位"起点范围 [MIN_BASIC, S - MIN_BASIC - scrap_len]
    low = MIN_BASIC
    high = S - MIN_BASIC - scrap_len
    attempts = 0
    while len(defects) < n_def and attempts < 500:
        attempts += 1
        cand = round(rng.uniform(low, high), 1)
        # 与已有零废段保持 >= MIN_BASIC 间距（即干净坯段 >= MIN_BASIC）
        ok = True
        for a, b in defects:
            if cand < b + MIN_BASIC and a < cand + scrap_len + MIN_BASIC:
                ok = False
                break
        if ok:
            defects.append([cand, round(cand + scrap_len, 1)])
    defects.sort()

    inst: dict[str, Any] = {
        "seed": seed,
        "process": PROCESS,
        "billet": {"total_length": S},
        "customer": {"target": T, "target_min": t_min, "target_max": t_max},
        "defects": defects,
        "limits": {
            "min_basic": MIN_BASIC,
            "max_basic": MAX_BASIC,
            "min_process": MIN_PROCESS,
            "max_process": MAX_PROCESS,
        },
    }
    return inst


def clean_segments(inst: dict[str, Any]) -> list[list[float]]:
    """返回干净坯段列表 [[start, length], ...]。

    零废段把 [0, S] 分成若干"干净坯段"，每段内部不含零废段、
    可被切成若干成品。零废段本身是强制报废。
    """
    S = float(inst["billet"]["total_length"])
    defects = [list((a, b)) for a, b in inst["defects"]] or []
    segs: list[list[float]] = []
    prev = 0.0
    for a, b in defects:
        segs.append([prev, a - prev])
        prev = b
    segs.append([prev, S - prev])
    return [s for s in segs if s[1] > 1e-9]


def _equal_split_scrap(inst: dict[str, Any]) -> float:
    """朴素"均匀等分"baseline 的总报废长度（用于验收 headroom）。"""
    import math

    from simulator import piece_scrap

    a = MIN_BASIC
    b = MAX_BASIC
    total = 0.0
    for _start, length in clean_segments(inst):
        n = max(1, math.ceil(length / b))
        while n > 1 and length / n < a:
            n -= 1
        while length / n > b:
            n += 1
        base = length / n
        pieces = [base] * n
        pieces[-1] = length - base * (n - 1)
        # 与 baseline/solver.py 的 partition() 完全同口径（每块 round 到 4 位）
        for c in pieces:
            total += piece_scrap(round(c, 4), inst)
    # 零废段强制报废（与 baseline/solver.py 的真实报废口径一致）
    for a0, b0 in inst["defects"] or []:
        total += (b0 - a0)
    return total


def _interesting_ok(inst: dict[str, Any], min_extra: float = 0.2, min_headroom: float = 0.1) -> bool:
    """验收：参考解必须严格优于朴素等分（存在真正的优化空间）。

    两层含义：
    1. 最优损失须显著超过"零废段强制报废"（即存在真正的余料损失）——
       若最优损失只等于零废段长度，说明实例能被"一块不多不少"地切成目标长度，
       没有优化空间。
    2. 朴素"均匀等分"baseline 须比参考解差 >= min_headroom（米）——
       否则该实例上 agent 无区分度（优化也拿不到收益），对 benchmark 无意义。
    另外保证至少存在一块干净坯段 >= min_basic（否则不可行）。
    """
    import ref_solver

    from simulator import validate

    ok_segs = clean_segments(inst)
    if not ok_segs or max(s[1] for s in ok_segs) < MIN_BASIC:
        return False
    ref_cuts = ref_solver.solve(inst)["cuts"]
    if not validate(inst, ref_cuts)[0]:
        return False
    ref_scrap = ref_solver.total_scrap(inst, ref_cuts)
    defect_total = sum(b - a for a, b in inst["defects"] or [])
    if ref_scrap < defect_total + min_extra:
        return False
    return _equal_split_scrap(inst) >= ref_scrap + min_headroom


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "data" / "instances"
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        (1, "easy"), (2, "easy"), (3, "medium"), (4, "medium"),
        (5, "medium"), (6, "hard"), (7, "hard"), (8, "hard"),
    ]
    for seed, difficulty in specs:
        inst = None
        for trial in range(600):
            s = seed + trial * 997
            cand = generate(s, difficulty)
            if _interesting_ok(cand):
                inst = cand
                break
        assert inst is not None, f"no acceptable instance for slot {seed}/{difficulty}"
        path = out_dir / f"instance_{seed}.json"
        path.write_text(json.dumps(inst, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"instance_{seed}.json  diff={difficulty}  S={inst['billet']['total_length']}  "
              f"T={inst['customer']['target']}  #defects={len(inst['defects'])}  seed={inst['seed']}")


if __name__ == "__main__":
    main()
