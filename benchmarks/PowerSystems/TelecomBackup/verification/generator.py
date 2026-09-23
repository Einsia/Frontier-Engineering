"""实例生成器：seed 固定，生成可复现的区域备电实例（JSON）。

参数语义：
- 区域 200m x 200m，栅格化为 nx*ny 栅格（默认 20x20 = 400）。
- 站点围绕 4 个聚类中心高斯散布（城区基站分布），坐标裁剪到区域内。
- 电源分组：对站点坐标做 K-Means（纯 Python），K = ceil(N/3.5)。
- 电池电量：每个电源 uniform(15, 30) kWh。
- 栅格需求：每个栅格 uniform(0, 1)（相对负载单位）。
- 覆盖参数：pt_dbm=20, n_exp=6（阈值 -105dBm 下站点良好覆盖半径约 120m）。
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

GRID = {"width": 200.0, "height": 200.0, "nx": 20, "ny": 20}
CLUSTER_CENTERS = [(50.0, 50.0), (150.0, 50.0), (50.0, 150.0), (150.0, 150.0)]
SITE_SIGMA = 20.0
BATTERY_RANGE = (15.0, 30.0)
P_SILENT = 0.05       # 静默功耗 (kW/站点)：便宜，休息保电收益大
P_WORK_BASE = 3.0    # 工作功耗基值 (kW/站点)：昂贵，全开惩罚明显
P_WORK_COEF = 3.0    # 工作功耗负载系数 (kW/负载比)
DEMAND_MAX = 1.0
SITE_CAP = 60.0
HORIZON = 96
DELTA_MIN = 5.0
PT_DBM = 20.0
N_EXP = 6.0
THRESHOLD = -105.0
COVERAGE_RATIO = 0.8


def _kmeans(points: list[tuple[float, float]], k: int, rng: random.Random,
            iters: int = 20) -> list[list[int]]:
    n = len(points)
    assert n >= k, "not enough sites for k groups"
    init = rng.sample(range(n), k)
    centers = [points[i] for i in init]
    assign: list[int] = [0] * n
    for _ in range(iters):
        for i, (x, y) in enumerate(points):
            assign[i] = min(
                range(k), key=lambda c: math.hypot(x - centers[c][0], y - centers[c][1])
            )
        new_centers = []
        for c in range(k):
            members = [points[i] for i in range(n) if assign[i] == c]
            if members:
                new_centers.append(
                    (sum(p[0] for p in members) / len(members),
                     sum(p[1] for p in members) / len(members))
                )
            else:
                new_centers.append(centers[c])
        centers = new_centers
    groups: list[list[int]] = [[] for _ in range(k)]
    for i, c in enumerate(assign):
        groups[c].append(i)
    return [g for g in groups if g]


def generate(seed: int, n_sites: int, n_clusters: int = 4) -> dict[str, Any]:
    rng = random.Random(seed)
    centers = rng.sample(CLUSTER_CENTERS, n_clusters)
    sites: list[list[float]] = []
    for _ in range(n_sites):
        cx, cy = rng.choice(centers)
        x = min(195.0, max(5.0, cx + rng.gauss(0.0, SITE_SIGMA)))
        y = min(195.0, max(5.0, cy + rng.gauss(0.0, SITE_SIGMA)))
        sites.append([round(x, 1), round(y, 1)])

    k = max(1, math.ceil(n_sites / 3.5))
    groups = _kmeans([(s[0], s[1]) for s in sites], k, rng=rng)
    battery = [round(rng.uniform(*BATTERY_RANGE), 1) for _ in groups]

    nx, ny = GRID["nx"], GRID["ny"]
    demand = [round(rng.uniform(0.0, DEMAND_MAX), 3) for _ in range(nx * ny)]

    inst: dict[str, Any] = {
        "seed": seed,
        "grid": GRID,
        "sites": sites,
        "groups": groups,
        "battery": battery,
        "demand": demand,
        "pt_dbm": PT_DBM,
        "n_exp": N_EXP,
        "threshold": THRESHOLD,
        "coverage_ratio": COVERAGE_RATIO,
        "delta_min": DELTA_MIN,
        "horizon": HORIZON,
        "site_cap": SITE_CAP,
        "p_silent": P_SILENT,
        "p_work_base": P_WORK_BASE,
        "p_work_coef": P_WORK_COEF,
    }
    return inst




def _stagger_ok(inst: dict[str, Any], min_gap: float = 0.25) -> bool:
    """验收：错峰调度（同时休息多路）须比全程开启好 >= min_gap。

    全程开启电池并行耗尽；让多路电源同时休息（其余保持负载分散）能大幅保电
    并延长总备电时长。实例几何/电池若不满足，则此实例对"调度"无意义，应重造。
    """
    from simulator import simulate

    horizon = int(inst["horizon"])
    k = len(inst["groups"])
    on_all = [[[0, horizon]] for _ in range(k)]
    ao = simulate(inst, on_all)
    best = ao
    for n_rest in (1, 2, 3):
        for r in (4, 8, 12, 16):
            on = [[] for _ in range(k)]
            slot = seg = 0
            while slot < horizon:
                for i in range(k):
                    if (seg + i) % k >= n_rest:
                        on[i].append([slot, min(slot + r, horizon)])
                slot += r
                seg += 1
            best = max(best, simulate(inst, on))
    return best >= ao * (1.0 + min_gap)

def main() -> None:
    out_dir = Path(__file__).resolve().parent / "data" / "instances"
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        (1, 20), (2, 24), (3, 28), (4, 32),
        (5, 36), (6, 40), (7, 24), (8, 32),
    ]
    for idx, (seed, n_sites) in enumerate(specs):
        inst = None
        for trial in range(300):
            s = seed + trial * 101
            cand = generate(s, n_sites)
            if _stagger_ok(cand):
                inst = cand
                break
        assert inst is not None, f"no acceptable instance for slot {idx}"
        path = out_dir / f"instance_{seed}.json"
        path.write_text(json.dumps(inst, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"instance_{seed}.json  N={n_sites}  K={len(inst['groups'])}  seed={inst['seed']}  (stagger ok)")


if __name__ == "__main__":
    main()
