from __future__ import annotations

import math
from collections import Counter
from typing import Any


def item_information(
    item: dict[str, Any],
    theta: float,
) -> float:
    """二参数逻辑模型下，题目在某能力水平的测量信息量。"""
    discrimination = float(item["discrimination"])
    difficulty = float(item["difficulty"])

    value = discrimination * (theta - difficulty)
    value = max(-60.0, min(60.0, value))

    probability = 1.0 / (1.0 + math.exp(-value))

    return (
        discrimination
        * discrimination
        * probability
        * (1.0 - probability)
    )


def validate_selection(
    problem: dict[str, Any],
    selected_ids: Any,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    errors: list[str] = []
    items_by_id = {
        item["id"]: item
        for item in problem["items"]
    }

    if not isinstance(selected_ids, list):
        selected_ids = []
        errors.append("selected_ids 必须是列表")

    clean_ids: list[int] = []

    for item_id in selected_ids:
        if isinstance(item_id, bool) or not isinstance(item_id, int):
            errors.append(f"非法题号类型：{item_id!r}")
        elif item_id not in items_by_id:
            errors.append(f"未知题号：{item_id}")
        else:
            clean_ids.append(item_id)

    if len(selected_ids) != problem["test_length"]:
        errors.append(
            f"题目总数错误：要求 {problem['test_length']}，"
            f"实际 {len(selected_ids)}"
        )

    if len(clean_ids) != len(set(clean_ids)):
        errors.append("存在重复题号")

    unique_ids = list(dict.fromkeys(clean_ids))
    selected = [
        items_by_id[item_id]
        for item_id in unique_ids
    ]

    domain_counts = Counter(
        item["domain"] for item in selected
    )

    for domain, target in problem["domain_targets"].items():
        actual = domain_counts.get(domain, 0)

        if actual != target:
            errors.append(
                f"{domain} 数量错误：要求 {target}，实际 {actual}"
            )

    enemy_counts = Counter(
        item["enemy_group"]
        for item in selected
        if item["enemy_group"] is not None
    )

    enemy_conflicts = {
        group: count
        for group, count in enemy_counts.items()
        if count > problem["max_items_per_enemy_group"]
    }

    if enemy_conflicts:
        errors.append(f"存在材料冲突：{enemy_conflicts}")

    total_time = sum(
        item["time"] for item in selected
    )

    if selected:
        mean_dif = sum(
            item["dif_risk"] for item in selected
        ) / len(selected)

        mean_exposure = sum(
            item["exposure"] for item in selected
        ) / len(selected)
    else:
        mean_dif = 1.0
        mean_exposure = 1.0

    if total_time > problem["max_total_time"]:
        errors.append(
            f"总时间超限：{total_time} > "
            f"{problem['max_total_time']}"
        )

    if mean_dif > problem["max_mean_dif"]:
        errors.append(
            f"平均 DIF 风险超限：{mean_dif:.4f} > "
            f"{problem['max_mean_dif']:.4f}"
        )

    if mean_exposure > problem["max_mean_exposure"]:
        errors.append(
            f"平均曝光率超限：{mean_exposure:.4f} > "
            f"{problem['max_mean_exposure']:.4f}"
        )

    stats = {
        "selected_count": len(selected_ids),
        "domain_counts": dict(domain_counts),
        "total_time": total_time,
        "time_limit": problem["max_total_time"],
        "mean_dif": mean_dif,
        "dif_limit": problem["max_mean_dif"],
        "mean_exposure": mean_exposure,
        "exposure_limit": problem["max_mean_exposure"],
        "enemy_conflicts": enemy_conflicts,
    }

    return selected, errors, stats


def score_selection(
    problem: dict[str, Any],
    selected_ids: Any,
) -> dict[str, Any]:
    selected, errors, stats = validate_selection(
        problem,
        selected_ids,
    )

    if not selected:
        return {
            "valid": False,
            "errors": errors,
            "objective": 0.0,
            "components": {},
            **stats,
        }

    information_curve = [
        sum(
            item_information(item, theta)
            for item in selected
        ) / len(selected)
        for theta in problem["theta_points"]
    ]

    weighted_information = sum(
        weight * information
        for weight, information in zip(
            problem["theta_weights"],
            information_curve,
        )
    )

    worst_information = min(information_curve)
    mean_information = (
        sum(information_curve)
        / len(information_curve)
    )

    profile_balance = (
        worst_information / mean_information
        if mean_information > 0
        else 0.0
    )

    available_strands = {
        (item["domain"], item["content_strand"])
        for item in problem["items"]
    }

    selected_strands = {
        (item["domain"], item["content_strand"])
        for item in selected
    }

    strand_coverage = (
        len(selected_strands) / len(available_strands)
    )

    time_efficiency = max(
        0.0,
        1.0
        - stats["total_time"] / problem["max_total_time"],
    )

    dif_quality = max(
        0.0,
        1.0 - stats["mean_dif"],
    )

    exposure_quality = max(
        0.0,
        1.0 - stats["mean_exposure"],
    )

    objective = (
        0.50 * weighted_information
        + 0.22 * worst_information
        + 0.08 * profile_balance
        + 0.08 * dif_quality
        + 0.05 * exposure_quality
        + 0.03 * time_efficiency
        + 0.04 * strand_coverage
    )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "objective": objective,
        "components": {
            "information_curve": [
                round(value, 6)
                for value in information_curve
            ],
            "weighted_information": round(
                weighted_information,
                6,
            ),
            "worst_information": round(
                worst_information,
                6,
            ),
            "profile_balance": round(
                profile_balance,
                6,
            ),
            "strand_coverage": round(
                strand_coverage,
                6,
            ),
            "time_efficiency": round(
                time_efficiency,
                6,
            ),
            "dif_quality": round(
                dif_quality,
                6,
            ),
            "exposure_quality": round(
                exposure_quality,
                6,
            ),
        },
        **stats,
    }
