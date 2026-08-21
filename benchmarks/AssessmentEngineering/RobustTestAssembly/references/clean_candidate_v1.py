from __future__ import annotations

import argparse
import importlib.util
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


TASK_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = (
    TASK_ROOT
    / "references"
    / "baseline_init_v1.py"
)


def load_baseline_module() -> Any:
    """读取公开的普通初始算法，不读取裁判。"""
    spec = importlib.util.spec_from_file_location(
        "frozen_baseline",
        BASELINE_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError("无法读取普通初始算法")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def item_information(
    item: dict[str, Any],
    theta: float,
) -> float:
    """估计一道题在某个能力水平上的测量信息量。"""
    discrimination = float(item["discrimination"])
    difficulty = float(item["difficulty"])

    value = discrimination * (theta - difficulty)
    value = max(-60.0, min(60.0, value))

    probability = 1.0 / (
        1.0 + math.exp(-value)
    )

    return (
        discrimination
        * discrimination
        * probability
        * (1.0 - probability)
    )


def is_valid(
    problem: dict[str, Any],
    selected_ids: list[int],
) -> bool:
    """根据公开规则判断一套组卷方案是否合法。"""
    if len(selected_ids) != problem["test_length"]:
        return False

    if len(selected_ids) != len(set(selected_ids)):
        return False

    items_by_id = {
        item["id"]: item
        for item in problem["items"]
    }

    if any(
        item_id not in items_by_id
        for item_id in selected_ids
    ):
        return False

    selected = [
        items_by_id[item_id]
        for item_id in selected_ids
    ]

    domain_counts = Counter(
        item["domain"] for item in selected
    )

    for domain, target in (
        problem["domain_targets"].items()
    ):
        if domain_counts.get(domain, 0) != target:
            return False

    enemy_counts = Counter(
        item["enemy_group"]
        for item in selected
        if item["enemy_group"] is not None
    )

    if any(
        count
        > problem["max_items_per_enemy_group"]
        for count in enemy_counts.values()
    ):
        return False

    total_time = sum(
        item["time"] for item in selected
    )

    mean_dif = sum(
        item["dif_risk"] for item in selected
    ) / len(selected)

    mean_exposure = sum(
        item["exposure"] for item in selected
    ) / len(selected)

    return (
        total_time <= problem["max_total_time"]
        and mean_dif <= problem["max_mean_dif"]
        and mean_exposure
        <= problem["max_mean_exposure"]
    )


def proxy_quality(
    problem: dict[str, Any],
    selected_ids: list[int],
) -> float:
    """
    使用独立设计的近似评价规则。

    它和正式裁判的权重并不相同，
    只依据公开的心理测量目标判断方案。
    """
    items_by_id = {
        item["id"]: item
        for item in problem["items"]
    }

    selected = [
        items_by_id[item_id]
        for item_id in selected_ids
    ]

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

    total_time = sum(
        item["time"] for item in selected
    )

    mean_dif = sum(
        item["dif_risk"] for item in selected
    ) / len(selected)

    mean_exposure = sum(
        item["exposure"] for item in selected
    ) / len(selected)

    available_strands = {
        (item["domain"], item["content_strand"])
        for item in problem["items"]
    }

    selected_strands = {
        (item["domain"], item["content_strand"])
        for item in selected
    }

    strand_coverage = (
        len(selected_strands)
        / len(available_strands)
    )

    time_efficiency = max(
        0.0,
        1.0
        - total_time / problem["max_total_time"],
    )

    # 这些权重故意不使用正式裁判的权重。
    return (
        0.48 * weighted_information
        + 0.25 * worst_information
        + 0.08 * profile_balance
        + 0.09 * (1.0 - mean_dif)
        + 0.05 * (1.0 - mean_exposure)
        + 0.03 * time_efficiency
        + 0.02 * strand_coverage
    )


def improve_selection(
    problem: dict[str, Any],
) -> list[int]:
    baseline = load_baseline_module()

    selected_ids = list(
        baseline.select_items(problem)
    )

    items_by_id = {
        item["id"]: item
        for item in problem["items"]
    }

    current_quality = proxy_quality(
        problem,
        selected_ids,
    )

    for _ in range(100):
        selected_set = set(selected_ids)

        best_ids: list[int] | None = None
        best_quality = current_quality

        for position, old_id in enumerate(
            selected_ids
        ):
            old_domain = (
                items_by_id[old_id]["domain"]
            )

            for new_item in problem["items"]:
                new_id = new_item["id"]

                # 只在同一领域内换题，
                # 避免破坏领域数量要求。
                if (
                    new_item["domain"]
                    != old_domain
                ):
                    continue

                if new_id in selected_set:
                    continue

                trial_ids = selected_ids.copy()
                trial_ids[position] = new_id

                if not is_valid(
                    problem,
                    trial_ids,
                ):
                    continue

                trial_quality = proxy_quality(
                    problem,
                    trial_ids,
                )

                if (
                    trial_quality
                    > best_quality + 1e-12
                ):
                    best_quality = trial_quality
                    best_ids = trial_ids

                elif (
                    abs(
                        trial_quality
                        - best_quality
                    )
                    <= 1e-12
                    and best_ids is not None
                    and tuple(trial_ids)
                    < tuple(best_ids)
                ):
                    best_ids = trial_ids

        if best_ids is None:
            break

        selected_ids = best_ids
        current_quality = best_quality

    return selected_ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--problem",
        required=True,
    )
    parser.add_argument(
        "--output",
        required=True,
    )
    args = parser.parse_args()

    problem = json.loads(
        Path(args.problem).read_text(
            encoding="utf-8",
        )
    )

    selected_ids = improve_selection(problem)

    Path(args.output).write_text(
        json.dumps(
            {
                "selected_ids": selected_ids,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
