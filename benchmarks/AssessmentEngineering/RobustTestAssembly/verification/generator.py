from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


DOMAINS = (
    "memory",
    "reasoning",
    "attention",
    "executive",
)

THETA_POINTS = (-1.5, -0.5, 0.5, 1.5)


SCENARIO_SPECS: dict[str, dict[str, Any]] = {
    "dev_balanced": {
        "seed": 6101,
        "feedback": True,
        "domain_targets": {
            "memory": 6,
            "reasoning": 6,
            "attention": 6,
            "executive": 6,
        },
        "theta_weights": [0.20, 0.30, 0.30, 0.20],
        "max_total_time": 78,
        "max_mean_dif": 0.42,
        "max_mean_exposure": 0.68,
    },
    "dev_low_ability_focus": {
        "seed": 6102,
        "feedback": True,
        "domain_targets": {
            "memory": 7,
            "reasoning": 6,
            "attention": 6,
            "executive": 5,
        },
        "theta_weights": [0.45, 0.30, 0.15, 0.10],
        "max_total_time": 80,
        "max_mean_dif": 0.40,
        "max_mean_exposure": 0.68,
    },
    "dev_high_ability_focus": {
        "seed": 6103,
        "feedback": True,
        "domain_targets": {
            "memory": 5,
            "reasoning": 7,
            "attention": 5,
            "executive": 7,
        },
        "theta_weights": [0.10, 0.15, 0.30, 0.45],
        "max_total_time": 80,
        "max_mean_dif": 0.40,
        "max_mean_exposure": 0.68,
    },
    "dev_fast_screening": {
        "seed": 6104,
        "feedback": True,
        "domain_targets": {
            "memory": 6,
            "reasoning": 6,
            "attention": 7,
            "executive": 5,
        },
        "theta_weights": [0.20, 0.30, 0.30, 0.20],
        "max_total_time": 65,
        "max_mean_dif": 0.43,
        "max_mean_exposure": 0.70,
    },
    "dev_fairness_sensitive": {
        "seed": 6105,
        "feedback": True,
        "domain_targets": {
            "memory": 6,
            "reasoning": 6,
            "attention": 6,
            "executive": 6,
        },
        "theta_weights": [0.25, 0.25, 0.25, 0.25],
        "max_total_time": 80,
        "max_mean_dif": 0.27,
        "max_mean_exposure": 0.68,
    },
    "dev_security_sensitive": {
        "seed": 6106,
        "feedback": True,
        "domain_targets": {
            "memory": 6,
            "reasoning": 6,
            "attention": 6,
            "executive": 6,
        },
        "theta_weights": [0.20, 0.30, 0.30, 0.20],
        "max_total_time": 80,
        "max_mean_dif": 0.42,
        "max_mean_exposure": 0.43,
    },
    "validation_mixed_a": {
        "seed": 7101,
        "feedback": False,
        "domain_targets": {
            "memory": 7,
            "reasoning": 5,
            "attention": 6,
            "executive": 6,
        },
        "theta_weights": [0.35, 0.30, 0.20, 0.15],
        "max_total_time": 73,
        "max_mean_dif": 0.34,
        "max_mean_exposure": 0.55,
    },
    "validation_mixed_b": {
        "seed": 7102,
        "feedback": False,
        "domain_targets": {
            "memory": 5,
            "reasoning": 7,
            "attention": 6,
            "executive": 6,
        },
        "theta_weights": [0.15, 0.20, 0.30, 0.35],
        "max_total_time": 72,
        "max_mean_dif": 0.35,
        "max_mean_exposure": 0.54,
    },
    "validation_mixed_c": {
        "seed": 7103,
        "feedback": False,
        "domain_targets": {
            "memory": 6,
            "reasoning": 6,
            "attention": 7,
            "executive": 5,
        },
        "theta_weights": [0.25, 0.35, 0.25, 0.15],
        "max_total_time": 68,
        "max_mean_dif": 0.32,
        "max_mean_exposure": 0.58,
    },
    "validation_mixed_d": {
        "seed": 7104,
        "feedback": False,
        "domain_targets": {
            "memory": 6,
            "reasoning": 6,
            "attention": 5,
            "executive": 7,
        },
        "theta_weights": [0.15, 0.25, 0.30, 0.30],
        "max_total_time": 70,
        "max_mean_dif": 0.33,
        "max_mean_exposure": 0.52,
    },
}


def generate_item_bank(seed: int) -> list[dict[str, Any]]:
    """生成包含80道模拟题的稳定题库。"""
    rng = random.Random(seed)
    items: list[dict[str, Any]] = []

    for domain_index, domain in enumerate(DOMAINS):
        for local_index in range(20):
            item_id = domain_index * 20 + local_index + 1

            # 前16道题两两共享材料，因此同组最多选一道；
            # 最后4道题没有材料冲突。
            if local_index < 16:
                enemy_group: str | None = (
                    f"{domain}_material_{local_index // 2 + 1}"
                )
            else:
                enemy_group = None

            item = {
                "id": item_id,
                "domain": domain,
                "content_strand": (
                    f"{domain}_strand_{local_index % 4 + 1}"
                ),
                "time": rng.randint(2, 5),
                "discrimination": round(
                    rng.uniform(0.65, 2.15),
                    4,
                ),
                "difficulty": round(
                    rng.uniform(-2.4, 2.4),
                    4,
                ),
                "dif_risk": round(
                    min(
                        0.95,
                        max(
                            0.01,
                            rng.betavariate(1.6, 4.2),
                        ),
                    ),
                    4,
                ),
                "exposure": round(
                    min(
                        0.98,
                        max(
                            0.02,
                            rng.betavariate(2.0, 3.0),
                        ),
                    ),
                    4,
                ),
                "enemy_group": enemy_group,
            }
            items.append(item)

    return items


def generate_scenario(name: str) -> dict[str, Any]:
    if name not in SCENARIO_SPECS:
        available = ", ".join(SCENARIO_SPECS)
        raise ValueError(
            f"未知场景：{name}。可选场景：{available}"
        )

    spec = SCENARIO_SPECS[name]

    return {
        "problem_version": "v1-draft",
        "scenario": name,
        "seed": spec["seed"],
        "feedback": spec["feedback"],
        "test_length": sum(
            spec["domain_targets"].values()
        ),
        "domain_targets": spec["domain_targets"],
        "theta_points": list(THETA_POINTS),
        "theta_weights": spec["theta_weights"],
        "max_total_time": spec["max_total_time"],
        "max_mean_dif": spec["max_mean_dif"],
        "max_mean_exposure": spec["max_mean_exposure"],
        "max_items_per_enemy_group": 1,
        "items": generate_item_bank(spec["seed"]),
    }


def print_summary() -> None:
    rows = []

    for name, spec in SCENARIO_SPECS.items():
        rows.append(
            {
                "scenario": name,
                "seed": spec["seed"],
                "feedback": spec["feedback"],
                "test_length": sum(
                    spec["domain_targets"].values()
                ),
                "domain_targets": spec["domain_targets"],
                "max_total_time": spec["max_total_time"],
                "max_mean_dif": spec["max_mean_dif"],
                "max_mean_exposure": (
                    spec["max_mean_exposure"]
                ),
            }
        )

    print(
        json.dumps(
            rows,
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--scenario")
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.summary:
        print_summary()
        return

    if not args.scenario or not args.output:
        parser.error(
            "生成场景时必须同时提供 "
            "--scenario 和 --output"
        )

    scenario = generate_scenario(args.scenario)

    Path(args.output).write_text(
        json.dumps(
            scenario,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
