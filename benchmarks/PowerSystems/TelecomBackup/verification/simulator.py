"""计分模拟器：验证候选电源开关策略，返回备电时长（分钟）。

规则（自编简化模型，物理语义见 Task.md / README）：
- 区域为 nx*ny 个栅格；N 个站点；K 个电源，每组站点共用一个电池。
- 覆盖电平 P(g, s) = pt_dbm - 10*n_exp*log10(d(g,s)+1)（dBm，d 为米）。
- 栅格接入"最强存活站点"；栅格"良好"当且仅当 max P(g,s) > threshold。
- 站点功耗（由实例提供，默认见下）：工作 P_work = p_work_base + p_work_coef*min(load_s/site_cap, 1.0) kW；静默 p_silent kW。
  实例自带校准（当前数据：p_silent=0.05, p_work_base=3.0, p_work_coef=3.0），保证错峰调度有明显收益。
- 负载迁移：电源关闭 -> 站点静默（不提供覆盖，仍耗静默电）-> 栅格即时接入最强存活站点。
- 电源 k 在时隙 t > close_time[k] 时关闭；电量 E_k 每时隙扣 dt*sum(P)，耗尽 -> 停服（不耗电不覆盖）。
- 备电时长 = 首次覆盖比例 < coverage_ratio 的时隙的上一时刻（分钟）；撑满 horizon 则 T*delta_min。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# 默认参数（与 generator.py 保持一致）
PT_DBM = 20.0
N_EXP = 6.0
THRESHOLD = -105.0
COVERAGE_RATIO = 0.8
DELTA_MIN = 5.0
SITE_CAP = 60.0


def load_instance(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_power(inst: dict[str, Any]) -> list[list[float]]:
    """返回 (N, G) 的覆盖电平矩阵 P(s, g)（dBm）。"""
    grid = inst["grid"]
    nx, ny = grid["nx"], grid["ny"]
    w, h = grid["width"], grid["height"]
    pt = float(inst.get("pt_dbm", PT_DBM))
    n_exp = float(inst.get("n_exp", N_EXP))
    centers = [
        ((ix + 0.5) * w / nx, (iy + 0.5) * h / ny) for iy in range(ny) for ix in range(nx)
    ]
    rows: list[list[float]] = []
    for sx, sy in inst["sites"]:
        row = [
            pt - 10.0 * n_exp * math.log10(math.hypot(sx - cx, sy - cy) + 1.0)
            for cx, cy in centers
        ]
        rows.append(row)
    return rows


def _assign(power: list[list[float]], served: list[int], demand: list[float],
            threshold: float) -> tuple[list[float], int]:
    """给每个栅格接入最强存活站点；返回 (每站点负载, 良好栅格数)。"""
    n_sites = len(power)
    n_cells = len(demand)
    best_val = [-1e9] * n_cells
    best_site = [-1] * n_cells
    for s in served:
        prow = power[s]
        for g in range(n_cells):
            v = prow[g]
            if v > best_val[g]:
                best_val[g] = v
                best_site[g] = s
    load = [0.0] * n_sites
    good = 0
    for g in range(n_cells):
        if best_val[g] > threshold:
            good += 1
        s = best_site[g]
        if s >= 0:
            load[s] += demand[g]
    return load, good


def _normalize_intervals(intervals: list[list[int]], horizon: int) -> list[list[int]]:
    """合并重叠/相邻区间并排序，返回升序不交区间 [a, b)。"""
    ivs = sorted((a, b) for a, b in intervals if a < b)
    merged: list[list[int]] = []
    for a, b in ivs:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def simulate(inst: dict[str, Any], on_intervals: list[list[list[int]]]) -> float:
    """返回备电时长（分钟）。

    on_intervals[k] = 电源 k 的开启时隙区间列表，如 [[0, 48], [60, 96]]，
    表示时隙 0..47 与 60..95 开启（时隙 0-index，半开区间 [a, b)）。
    on_intervals[k] = [[0, horizon]] 表示永不关闭；[] 表示一开始就关。
    """
    power = build_power(inst)
    groups: list[list[int]] = inst["groups"]
    demand: list[float] = inst["demand"]
    # 功耗参数由实例提供（数据自带校准）：静默功耗、工作基值、工作负载系数。
    p_silent = float(inst.get("p_silent", 1.0))
    p_work_base = float(inst.get("p_work_base", 1.2))
    p_work_coef = float(inst.get("p_work_coef", 2.0))
    threshold = float(inst.get("threshold", THRESHOLD))
    coverage_ratio = float(inst.get("coverage_ratio", COVERAGE_RATIO))
    delta_min = float(inst.get("delta_min", DELTA_MIN))
    site_cap = float(inst.get("site_cap", SITE_CAP))
    horizon = int(inst["horizon"])
    n_cells = len(demand)
    n_sites = len(inst["sites"])
    required_good = coverage_ratio * n_cells
    dt_hour = delta_min / 60.0

    # 预计算每时隙每电源开关状态（K x horizon 布尔）
    on_states: list[list[bool]] = []
    for k in range(len(groups)):
        ivs = _normalize_intervals(on_intervals[k], horizon)
        row = [False] * horizon
        for a, b in ivs:
            for s in range(max(0, a), min(b, horizon)):
                row[s] = True
        on_states.append(row)

    def work_sites(slot: int, battery: list[float]) -> list[int]:
        served: list[int] = []
        for k in range(len(groups)):
            if on_states[k][slot] and battery[k] > 0:
                served.extend(groups[k])
        return served

    battery = [float(e) for e in inst["battery"]]
    for slot in range(horizon):
        # 本时隙开始时的工作站点（扣电前）
        served_now = work_sites(slot, battery)
        load, _ = _assign(power, served_now, demand, threshold)
        # 电量推进
        for k in range(len(groups)):
            if battery[k] <= 0:
                continue
            e_k = 0.0
            for s in groups[k]:
                if on_states[k][slot]:
                    load_ratio = min(load[s] / site_cap, 1.0)
                    e_k += p_work_base + p_work_coef * load_ratio  # 工作功耗
                else:
                    e_k += p_silent  # 静默功耗
            battery[k] -= dt_hour * e_k
        # 扣电后覆盖检查
        served_after = work_sites(slot, battery)
        _, good = _assign(power, served_after, demand, threshold)
        if good < required_good:
            return slot * delta_min
    return horizon * delta_min
