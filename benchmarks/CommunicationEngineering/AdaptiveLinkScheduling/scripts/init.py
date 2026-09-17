from __future__ import annotations

from typing import Any


def _choose_mcs(snr_db: float, mcs_table: list[dict[str, Any]], margin_db: float = 2.0) -> int:
    selected = int(mcs_table[0]["mcs"])
    for item in mcs_table:
        if snr_db >= float(item["snr_threshold_db"]) + margin_db:
            selected = int(item["mcs"])
    return selected


def schedule_frame(frame: dict[str, Any]) -> list[dict[str, float | int]]:
    """Return one scheduling decision per resource block."""

    # EVOLVE-BLOCK-START
    users = frame["users"]
    mcs_table = frame["mcs_table"]
    num_rbs = int(frame["num_resource_blocks"])
    power_min = float(frame["power_min_dbm"])
    power_max = float(frame["power_max_dbm"])
    nominal_power = min(power_max, max(power_min, 20.0))

    remaining = {int(user["id"]): float(user["queue_bits"]) for user in users}
    served = {int(user["id"]): 0.0 for user in users}
    decisions: list[dict[str, float | int]] = []

    for rb in range(num_rbs):
        best_user = None
        best_score = None
        for user in users:
            user_id = int(user["id"])
            if remaining[user_id] <= 0:
                continue
            snr = float(user["snr_estimate_db"][rb])
            latency = float(user["latency_weight"])
            deficit = max(0.0, float(user["min_service_bits"]) - served[user_id])
            score = snr + 3.0 * latency + 0.002 * deficit + 0.0005 * remaining[user_id]
            if best_score is None or score > best_score:
                best_score = score
                best_user = user

        if best_user is None:
            decisions.append({"user": int(users[0]["id"]), "mcs": 0, "power_dbm": power_min})
            continue

        user_id = int(best_user["id"])
        snr_at_power = float(best_user["snr_estimate_db"][rb]) + (nominal_power - 20.0)
        mcs = _choose_mcs(snr_at_power, mcs_table, margin_db=2.0)
        bits = 0.0
        for item in mcs_table:
            if int(item["mcs"]) == int(mcs):
                bits = float(item["bits_per_rb"])
                break
        delivered_estimate = min(bits, remaining[user_id])
        remaining[user_id] -= delivered_estimate
        served[user_id] += delivered_estimate
        decisions.append({"user": user_id, "mcs": int(mcs), "power_dbm": nominal_power})

    return decisions
    # EVOLVE-BLOCK-END


if __name__ == "__main__":
    demo = {
        "num_resource_blocks": 2,
        "power_min_dbm": 5.0,
        "power_max_dbm": 24.0,
        "mcs_table": [
            {"mcs": 0, "snr_threshold_db": -3.0, "bits_per_rb": 180},
            {"mcs": 1, "snr_threshold_db": 1.0, "bits_per_rb": 300},
        ],
        "users": [
            {"id": 0, "queue_bits": 1000, "latency_weight": 1.0, "min_service_bits": 200, "snr_estimate_db": [2.0, 1.0]},
            {"id": 1, "queue_bits": 800, "latency_weight": 1.4, "min_service_bits": 200, "snr_estimate_db": [0.0, 4.0]},
        ],
    }
    print(schedule_frame(demo))
