"""在线切割实例生成器：种子生成隐藏异常表（不进 agent 可见实例）。

参数语义：
- 浇铸时长 T_cast 决定总材料长度 S = v*T_cast（流坐标 [0, S]）。
- 隐藏异常由 anomaly_seed 确定性生成（position、scrap_len 固定 0.8m），
  在 process.reveal_lead 确定的提前量下"逐步揭示"给 agent。
- 实例 JSON 含 `defects`（隐藏表，仅供 simulator/参考解使用）；
  `strip_for_agent(inst)` 会去掉 defects/anomaly_seed，得到 agent 可见的版本。
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

MIN_BASIC = 4.8
MAX_BASIC = 12.6
LIMITS = {"min_basic": 4.8, "max_basic": 12.6, "min_process": 8.0, "max_process": 11.6}


def generate(seed: int, difficulty: str = "medium", reveal_lead: float = 10.0,
             n_anomaly: int | None = None) -> dict[str, Any]:
    rng = random.Random(seed * 10007 + 11)
    if difficulty == "easy":
        s_lo, s_hi, a_lo, a_hi = 60.0, 90.0, 1, 3
    elif difficulty == "hard":
        s_lo, s_hi, a_lo, a_hi = 120.0, 180.0, 6, 12
    else:
        s_lo, s_hi, a_lo, a_hi = 80.0, 130.0, 3, 7

    S = round(rng.uniform(s_lo, s_hi), 2)
    n = n_anomaly if n_anomaly is not None else rng.randint(a_lo, a_hi)
    T = float(rng.choice([8.5, 9.5, 11.1]))
    t_min, t_max = T - 0.5, T + 0.5

    scrap_len = 0.8
    defects: list[list[float]] = []
    # 生成异常位置：彼此与两端都留出 >= min_basic 的干净材料（保证每段可切、可污染）
    low = MIN_BASIC
    high = S - MIN_BASIC - scrap_len
    attempts = 0
    while len(defects) < n and attempts < 800:
        attempts += 1
        cand = round(rng.uniform(low, high), 2)
        ok = True
        for a, b in defects:
            if cand < b + MIN_BASIC and a < cand + scrap_len + MIN_BASIC:
                ok = False
                break
        if ok:
            defects.append([cand, round(cand + scrap_len, 2)])
    defects.sort()

    # 每 1000 米诞生一个异常不现实——这里按"异常密度"换算为浇铸时长。
    # T_cast 取 S/v + 充分裕量，确保整根材料都在观测范围内。
    v = 1.0
    t_cast = round(S / v + 120.0, 2)

    inst: dict[str, Any] = {
        "seed": seed,
        "anomaly_seed": seed + 100000,
        "process": {"v": v, "tc": 3, "tr": 1, "buffer_len": 60.0,
                    "scrap_len": scrap_len, "reveal_lead": reveal_lead},
        "cast": {"total_length": S, "t_cast": t_cast},
        "customer": {"target": T, "target_min": t_min, "target_max": t_max},
        "limits": LIMITS,
        "defects": defects,
    }
    return inst


def strip_for_agent(inst: dict[str, Any]) -> dict[str, Any]:
    """agent 可见版本：不含隐藏异常表/异常种子。"""
    out = dict(inst)
    out.pop("defects", None)
    out.pop("anomaly_seed", None)
    return out


def _drivable(inst: dict[str, Any]) -> bool:
    return bool(inst["defects"]) and float(inst["cast"]["total_length"]) > 30.0


if __name__ == "__main__":
    import sys as _s
    if len(_s.argv) < 2:
        print("usage: python generator.py <out.json> [difficulty] [reveal_lead]", file=_s.stderr)
        raise SystemExit(2)
    out = Path(_s.argv[1])
    diff = _s.argv[2] if len(_s.argv) > 2 else "medium"
    rl = float(_s.argv[3]) if len(_s.argv) > 3 else 60.0
    inst = generate(1, diff, rl)
    out.write_text(json.dumps(inst, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}  S={inst['cast']['total_length']}  #defects={len(inst['defects'])}  reveal_lead={rl}")
