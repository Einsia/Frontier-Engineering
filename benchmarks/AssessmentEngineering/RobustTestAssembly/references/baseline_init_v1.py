# EVOLVE-BLOCK-START
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def item_information(
    item: dict[str, Any],
    theta: float,
) -> float:
    """计算一道题在某个能力水平上的测量信息量。"""
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


def item_value(
    item: dict[str, Any],
    problem: dict[str, Any],
) -> float:
    """给单道题计算一个简单的初始吸引力分数。"""
    information = [
        item_information(item, theta)
        for theta in problem["theta_points"]
    ]

    weighted_information = sum(
        weight * value
        for weight, value in zip(
            problem["theta_weights"],
            information,
        )
    )

    weakest_information = min(information)

    time_penalty = (
        3.0
        * item["time"]
        / problem["max_total_time"]
    )

    dif_penalty = (
        0.50
        * item["dif_risk"]
        / problem["max_mean_dif"]
    )

    exposure_penalty = (
        0.30
        * item["exposure"]
        / problem["max_mean_exposure"]
    )

    return (
        weighted_information
        + 0.20 * weakest_information
        - time_penalty
        - dif_penalty
        - exposure_penalty
    )


def constraint_values(
    selected: list[dict[str, Any]],
) -> tuple[float, float, float]:
    total_time = sum(item["time"] for item in selected)

    mean_dif = sum(
        item["dif_risk"] for item in selected
    ) / len(selected)

    mean_exposure = sum(
        item["exposure"] for item in selected
    ) / len(selected)

    return total_time, mean_dif, mean_exposure


def violation_amount(
    selected: list[dict[str, Any]],
    problem: dict[str, Any],
) -> float:
    total_time, mean_dif, mean_exposure = (
        constraint_values(selected)
    )

    return (
        max(
            0.0,
            total_time / problem["max_total_time"] - 1.0,
        )
        + max(
            0.0,
            mean_dif / problem["max_mean_dif"] - 1.0,
        )
        + max(
            0.0,
            mean_exposure
            / problem["max_mean_exposure"]
            - 1.0,
        )
    )


def solution_quality(
    selected: list[dict[str, Any]],
    problem: dict[str, Any],
) -> float:
    information_by_theta = [
        sum(
            item_information(item, theta)
            for item in selected
        )
        for theta in problem["theta_points"]
    ]

    weighted_information = sum(
        weight * value
        for weight, value in zip(
            problem["theta_weights"],
            information_by_theta,
        )
    )

    return (
        weighted_information
        + 0.20 * min(information_by_theta)
    )


def respects_enemy_groups(
    selected: list[dict[str, Any]],
) -> bool:
    seen: set[str] = set()

    for item in selected:
        group = item["enemy_group"]

        if group is None:
            continue

        if group in seen:
            return False

        seen.add(group)

    return True


def select_items(
    problem: dict[str, Any],
) -> list[int]:
    selected: list[dict[str, Any]] = []

    # 第一阶段：每个领域分别进行简单贪心选择。
    for domain, required_count in (
        problem["domain_targets"].items()
    ):
        candidates = [
            item
            for item in problem["items"]
            if item["domain"] == domain
        ]

        chosen: list[dict[str, Any]] = []
        used_enemy_groups: set[str] = set()

        while len(chosen) < required_count:
            available = []

            for item in candidates:
                if item in chosen:
                    continue

                group = item["enemy_group"]

                if (
                    group is not None
                    and group in used_enemy_groups
                ):
                    continue

                available.append(item)

            if not available:
                raise RuntimeError(
                    f"领域 {domain} 没有足够的合法题目"
                )

            best_item = max(
                available,
                key=lambda item: (
                    item_value(item, problem),
                    -item["time"],
                    -item["dif_risk"],
                    -item["exposure"],
                    -item["id"],
                ),
            )

            chosen.append(best_item)

            if best_item["enemy_group"] is not None:
                used_enemy_groups.add(
                    best_item["enemy_group"]
                )

        selected.extend(chosen)

    # 第二阶段：如果整体限制超标，就进行同领域换题。
    for _ in range(200):
        current_violation = violation_amount(
            selected,
            problem,
        )

        if current_violation <= 1e-12:
            break

        current_quality = solution_quality(
            selected,
            problem,
        )
        selected_ids = {
            item["id"] for item in selected
        }

        best_swap = None

        for index, old_item in enumerate(selected):
            for new_item in problem["items"]:
                if new_item["domain"] != old_item["domain"]:
                    continue

                if new_item["id"] in selected_ids:
                    continue

                trial = selected.copy()
                trial[index] = new_item

                if not respects_enemy_groups(trial):
                    continue

                new_violation = violation_amount(
                    trial,
                    problem,
                )

                if new_violation >= current_violation:
                    continue

                quality_loss = (
                    current_quality
                    - solution_quality(trial, problem)
                )

                swap_key = (
                    new_violation,
                    quality_loss,
                    new_item["id"],
                )

                if (
                    best_swap is None
                    or swap_key < best_swap[0]
                ):
                    best_swap = (
                        swap_key,
                        index,
                        new_item,
                    )

        if best_swap is None:
            break

        _, index, new_item = best_swap
        selected[index] = new_item

    return [item["id"] for item in selected]


# EVOLVE-BLOCK-END

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    problem = json.loads(
        Path(args.problem).read_text(
            encoding="utf-8",
        )
    )

    selected_ids = select_items(problem)

    Path(args.output).write_text(
        json.dumps(
            {"selected_ids": selected_ids},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
