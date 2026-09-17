"""连铸切割在线模拟器（闭环、最小切段污染、揭示提前量）。

模型（详见 Task.md）：
- 材料用流坐标 x∈[0,S]，S = v*浇铸时长。横截面 x 到达切割点在 x/v + D/v。
- 隐藏异常（由 anomaly_seed 决定）：报废段占流区间 [x_a, x_a+scrap_len]。
- 揭示提前量 reveal_lead（米；v=1 时也等于"提前分钟数"）：一段报废料在
  x_a <= cut_pos + reveal_lead 时"揭示"给 agent；否则不可见。最终配置默认 reveal_lead=10
  （隐藏异常，信息不对称）；reveal_lead=60 为"忠实版"（τ_a 即知，60m 提前量，接近离线）；
  reveal_lead<max_basic 时制造"未知带"（信息不对称难度）。
- 最小切段污染：切割机每轮切割+回程对应 v*(tc+tr) 米；且能运走下限为 min_basic(4.8)。
  **物理上切不出 < min_basic 的块**，因此 0.8m 报废段必然被包在一个 >= min_basic 的
  污染块里、整块报废（不允许像离线版那样把报废段当 0.8m 小块切出）。
- 评分：scrap = 所有污染块长度 + 干净块超窗口报废 + 干净块 <min_process 整块报废；
  penalty = 干净块 |min(块长,target_max)-target|；
  util = 100*(S - (scrap + 1e-4*penalty))/S（微小破平，与离线口径一致），metric 保留精度。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

DEFAULTS = {
    "v": 1.0, "tc": 3, "tr": 1, "buffer_len": 60.0, "scrap_len": 0.8, "reveal_lead": 10.0,
    "min_basic": 4.8, "max_basic": 12.6, "min_process": 8.0, "max_process": 11.6,
}
SUM_TOL = 1e-3
OVERLAP_TOL = 1e-6


def load_instance(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _p(inst: dict[str, Any], key: str):
    proc = inst.get("process", {})
    return float(proc.get(key, DEFAULTS[key]))


def _limits(inst: dict[str, Any]) -> dict[str, float]:
    lim = inst.get("limits", {})
    return {
        "min_basic": float(lim.get("min_basic", DEFAULTS["min_basic"])),
        "max_basic": float(lim.get("max_basic", DEFAULTS["max_basic"])),
        "min_process": float(lim.get("min_process", DEFAULTS["min_process"])),
        "max_process": float(lim.get("max_process", DEFAULTS["max_process"])),
    }


def visible_defects(inst: dict[str, Any], cut_pos: float) -> list[dict[str, float]]:
    """返回 `cut_pos` 处 agent 可见的报废段（已揭示且未完全过去）。"""
    reveal = _p(inst, "reveal_lead")
    out: list[dict[str, float]] = []
    for xa, xb in inst.get("defects", []) or []:
        if xa <= cut_pos + reveal + OVERLAP_TOL and xb > cut_pos + OVERLAP_TOL:
            out.append({"x": xa, "x_end": xb})
    return out


def _make_state(inst: dict[str, Any], cut_pos: float, committed: list[float]) -> dict[str, Any]:
    cust = inst.get("customer", {})
    lim = _limits(inst)
    return {
        "cut_pos": round(cut_pos, 4),
        "committed": committed,
        "visible_defects": sorted(visible_defects(inst, cut_pos), key=lambda d: d["x"]),
        "total_length": float(inst["cast"]["total_length"]),
        "target": float(cust.get("target", 9.5)),
        "target_min": float(cust.get("target_min", 9.0)),
        "target_max": float(cust.get("target_max", 10.0)),
        "limits": {
            "min_basic": lim["min_basic"], "max_basic": lim["max_basic"],
            "min_process": lim["min_process"], "max_process": lim["max_process"],
        },
        "reveal_lead": _p(inst, "reveal_lead"),
    }


def partition(inst: dict[str, Any], decision_fn: Callable[[dict[str, Any]], float]) -> list[float]:
    """闭环推进：反复喂状态、取下一刀，直到切完；返回切段长度列表（之和 = S）。"""
    S = float(inst["cast"]["total_length"])
    lim = _limits(inst)
    committed: list[float] = []
    cut_pos = 0.0
    guard = 0
    while S - cut_pos > SUM_TOL and guard < 100000:
        guard += 1
        remaining = S - cut_pos
        if remaining <= lim["max_basic"] + SUM_TOL:
            # 最后一段 = 剩余材料（agent 不决定，直接收尾）
            piece = remaining
        else:
            L = decision_fn(_make_state(inst, cut_pos, list(committed)))
            # 校验可接受：非法/越界则回退到目标值夹取（保证推进）
            if not isinstance(L, (int, float)) or math.isnan(L) or math.isinf(L):
                L = cust_target(inst)
            L = float(L)
            piece = max(lim["min_basic"], min(lim["max_basic"], L))
            if piece > remaining:
                piece = remaining
        committed.append(round(piece, 4))
        cut_pos += piece
    return committed


def cust_target(inst: dict[str, Any]) -> float:
    return float(inst.get("customer", {}).get("target", 9.5))


def _piece_is_clean(piece_iv: tuple[float, float], defects: list[list[float]]) -> bool:
    (x0, x1) = piece_iv
    for xa, xb in defects:
        if x1 > xa + OVERLAP_TOL and x0 < xb - OVERLAP_TOL:
            return False  # 与任一报废段重叠 -> 污染
    return True


def score(inst: dict[str, Any], cuts: list[float]) -> tuple[bool, dict[str, Any]]:
    """给定整根切段，校验 + 评分。返回 (valid, metrics)。"""
    S = float(inst["cast"]["total_length"])
    lim = _limits(inst)
    if abs(sum(cuts) - S) > SUM_TOL:
        return False, {"valid": False, "reason": f"sum {sum(cuts)} != S {S}"}
    # 每块不得超过 [max_basic]；< min_basic 视为报废（尾段/短块物理上无法运走，作废）
    for c in cuts:
        if c > lim["max_basic"] + SUM_TOL:
            return False, {"valid": False, "reason": f"cut {c} exceeds max_basic"}

    defects = [list((a, b)) for a, b in inst.get("defects", []) or []]
    boundaries = [0.0]
    for c in cuts:
        boundaries.append(boundaries[-1] + c)
    total_scrap = 0.0
    total_penalty = 0.0
    for i, c in enumerate(cuts):
        if c < lim["min_basic"] - SUM_TOL:
            total_scrap += c  # 短块/尾段：物理无法运走，整块报废
            continue
        iv = (boundaries[i], boundaries[i + 1])
        if not _piece_is_clean(iv, defects):
            total_scrap += c  # 污染块整块报废
            continue
        # 干净块
        if c < lim["min_process"]:
            total_scrap += c  # <8.0 -> 整块报废
        else:
            total_scrap += max(0.0, c - float(inst["customer"]["target_max"]))
            total_penalty += abs(min(c, float(inst["customer"]["target_max"]))
                                 - float(inst["customer"]["target"]))
    # util 含极小贴合度惩罚（破平），与离线版口径一致：scrap 先、penalty 破平。
    # 保留到 4 位（不低于 penalty 量级），否则惩罚项会被 2 位舍入吞掉、破平失效。
    lam = float(inst.get("limits", {}).get("target_penalty_weight", 1e-4))
    util = max(0.0, 100.0 * (S - (total_scrap + lam * total_penalty)) / S)
    return True, {"valid": True, "scrap": round(total_scrap, 4),
                  "penalty": round(total_penalty, 4), "util": round(util, 4),
                  "cuts": cuts}
