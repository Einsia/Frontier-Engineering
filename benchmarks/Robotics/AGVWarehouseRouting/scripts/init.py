from __future__ import annotations

from typing import Any


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def plan_order(instance: dict[str, Any]) -> list[int]:
    """Return a permutation of pick ids for the AGV to visit."""

    # EVOLVE-BLOCK-START
    current = tuple(int(x) for x in instance["start"])
    remaining = [
        {
            "id": int(item["id"]),
            "pos": (int(item["row"]), int(item["col"])),
            "priority": float(item.get("priority", 1.0)),
        }
        for item in instance["picks"]
    ]
    goal = tuple(int(x) for x in instance["goal"])
    order: list[int] = []

    while remaining:
        def score(item: dict[str, Any]) -> float:
            dist = _manhattan(current, item["pos"])
            finish_bias = 0.20 * _manhattan(item["pos"], goal)
            priority_bonus = 2.0 * item["priority"]
            return dist + finish_bias - priority_bonus

        best = min(remaining, key=score)
        order.append(int(best["id"]))
        current = best["pos"]
        remaining = [item for item in remaining if int(item["id"]) != int(best["id"])]

    return order
    # EVOLVE-BLOCK-END


if __name__ == "__main__":
    demo = {
        "start": [0, 0],
        "goal": [0, 4],
        "picks": [
            {"id": 0, "row": 2, "col": 1, "priority": 1.0},
            {"id": 1, "row": 3, "col": 3, "priority": 1.0},
        ],
    }
    print(plan_order(demo))
