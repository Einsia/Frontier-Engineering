"""连铸切割计分模拟器：校验候选切割方案并给出评分。

规则（自编简化模型，物理语义见 Task.md / README）：
- 钢坯 = 一维线段 [0, S]；零废段（缺陷）必须被切出（强制报废）。
- 切口必须对齐每个零废段端点：任何一块"成品"都不能跨过零废段边界，
  否则该方案非法（零废段无法被单独切出）。
- 每块长度必须在 [min_basic, max_basic]；否则非法。
- 评分 = 总报废长度 + lambda * 总贴合度惩罚（lambda 极小，保证字典序：
  先最小化报废，再在同报废下让成品长度尽量贴近目标值 T）。

报废判定（对齐赛题原文）：
- c < min_process：送不到下道工序 -> 整块报废，scrap += c。
- c >= min_process：可送下道。超出 target_max 的部分报废，scrap += c - min(c, target_max)。
- target_min <= c <= target_max：零报废、零惩罚（完美块）。
- c < target_min（但 c >= min_process）：能送但偏短 -> 零报废、贴合度惩罚。

贴合度惩罚（惩罚项，用于同报废下的区分）：
- penalty = |min(c, target_max) - T|（即"实际交付长度"与目标值的距离）。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# 默认长度窗口（与 generator.py 保持一致）
MIN_BASIC = 4.8
MAX_BASIC = 12.6
MIN_PROCESS = 8.0
MAX_PROCESS = 11.6
# 贴合度惩罚权重（远小于 1m 报废，保证字典序：报废优先，贴合度仅破平）
TARGET_PENALTY_WEIGHT = 1e-4
SUM_TOL = 1e-3
BOUND_TOL = 1e-3


def load_instance(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _limits(inst: dict[str, Any]) -> dict[str, float]:
    lim = inst.get("limits", {})
    return {
        "min_basic": float(lim.get("min_basic", MIN_BASIC)),
        "max_basic": float(lim.get("max_basic", MAX_BASIC)),
        "min_process": float(lim.get("min_process", MIN_PROCESS)),
        "max_process": float(lim.get("max_process", MAX_PROCESS)),
    }


def clean_segments(inst: dict[str, Any]) -> list[list[float]]:
    """干净坯段列表 [[start, length], ...]（与 generator 一致，供参考解使用）。"""
    S = float(inst["billet"]["total_length"])
    defects = [list((a, b)) for a, b in inst["defects"]] or []
    segs: list[list[float]] = []
    prev = 0.0
    for a, b in defects:
        segs.append([prev, a - prev])
        prev = b
    segs.append([prev, S - prev])
    return [s for s in segs if s[1] > 1e-9]


def boundaries(cuts: list[float]) -> list[float]:
    """从 cut 长度列表求切点坐标（含 0 和 S）。"""
    b = [0.0]
    for c in cuts:
        b.append(b[-1] + c)
    return b


def piece_scrap(c: float, inst: dict[str, Any]) -> float:
    """单块长度 c 的报废长度（不含贴合度惩罚）。"""
    lim = _limits(inst)
    t_max = float(inst["customer"]["target_max"])
    if c < lim["min_process"]:
        return c
    return max(0.0, c - t_max)


def piece_penalty(c: float, inst: dict[str, Any]) -> float:
    """单块长度 c 的实际交付长度与目标值的距离（贴合度惩罚）。"""
    t = float(inst["customer"]["target"])
    t_max = float(inst["customer"]["target_max"])
    delivered = min(c, t_max)
    return abs(delivered - t)


def _is_defect_piece(l: float, r: float, defects: list[list[float]]) -> bool:
    """长度区间 [l, r) 是否恰好是某个零废段（允许其小于 min_basic）。"""
    for a, b in defects:
        if abs(l - a) <= BOUND_TOL and abs(r - b) <= BOUND_TOL:
            return True
    return False


def validate(inst: dict[str, Any], cuts: list[float]) -> tuple[bool, str]:
    """校验候选方案：sum 近似 S、每块在 [min_basic, max_basic]（零废段除外）、切口对齐零废段。"""
    lim = _limits(inst)
    S = float(inst["billet"]["total_length"])
    if not cuts or any((not isinstance(c, (int, float))) or math.isnan(c) or math.isinf(c) for c in cuts):
        return False, "empty or non-numeric cuts"
    if any(c <= 0 for c in cuts):
        return False, "non-positive cut"
    if abs(sum(cuts) - S) > SUM_TOL:
        return False, f"sum {sum(cuts)!r} != S {S!r} (tol {SUM_TOL})"

    defects = [list((a, b)) for a, b in inst["defects"]] or []
    b = boundaries(cuts)
    for i, c in enumerate(cuts):
        l, r = b[i], b[i + 1]
        in_range = (lim["min_basic"] - BOUND_TOL <= c <= lim["max_basic"] + BOUND_TOL)
        is_def = _is_defect_piece(l, r, defects)
        if not in_range and not is_def:
            return False, f"cut {c!r} out of [{lim['min_basic']}, {lim['max_basic']}] and not a defect"
    # 零废段端点必须是切点（否则成品跨零废段 / 零废段被切成不可运的碎块）
    for a, bb in defects:
        for e in (a, bb):
            if abs(e) > 1e-9 and abs(e - S) > 1e-9:
                if not any(abs(p - e) <= BOUND_TOL for p in b):
                    return False, f"cut does not isolate defect endpoint {e!r}"
    return True, "ok"


def score(inst: dict[str, Any], cuts: list[float], *, lam: float | None = None
          ) -> tuple[bool, dict[str, Any]]:
    """评分：返回 (valid, metrics)。metrics = {scrap, penalty, score, cuts}。"""
    ok, reason = validate(inst, cuts)
    if not ok:
        return False, {"valid": False, "reason": reason}

    # 零废段以独立小段表示（0.8m）：scrap(0.8)=0.8，不参与贴合度惩罚。
    defects = [list((a, b)) for a, b in inst["defects"]] or []
    b = boundaries(cuts)
    total_scrap = 0.0
    total_penalty = 0.0
    for i, c in enumerate(cuts):
        l, r = b[i], b[i + 1]
        total_scrap += piece_scrap(c, inst)
        if not _is_defect_piece(l, r, defects):
            total_penalty += piece_penalty(c, inst)

    lam = TARGET_PENALTY_WEIGHT if lam is None else float(lam)
    return True, {
        "valid": True,
        "scrap": round(total_scrap, 4),
        "penalty": round(total_penalty, 4),
        "score": round(total_scrap + lam * total_penalty, 4),
        "cuts": cuts,
    }


def solve_value(inst: dict[str, Any], cuts: list[float]) -> float:
    """便捷路由：无效 -> 返回极大值；有效 -> 返回 score。"""
    ok, m = score(inst, cuts)
    return m["score"] if ok else math.inf


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python simulator.py <instance.json>", file=sys.stderr)
        raise SystemExit(2)
    inst = load_instance(sys.argv[1])
    print(json.dumps({"clean_segments": clean_segments(inst),
                      "defects": inst["defects"]}, ensure_ascii=False, indent=1))
