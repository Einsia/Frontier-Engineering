# EVOLVE-BLOCK-START
from __future__ import annotations

from typing import Any, Mapping


def reset_policy() -> None:
    """Reset optional policy state between scenarios."""


def decide_quotes(observation: Mapping[str, Any]) -> dict[str, dict[str, float | int]]:
    """Return DUAL-market quote offsets and sizes for all three assets.

    The baseline uses a simple inventory skew: it makes additional buying less attractive
    when inventory is already positive, and makes selling more attractive to reduce it.
    """
    actions: dict[str, dict[str, float | int]] = {}
    for symbol, asset in observation["assets"].items():
        inventory = float(asset["dual_inventory"])
        mandate = str(asset["desk_mandate"]).lower()
        base = 16.0
        skew = 0.35 * inventory
        bid_offset = min(60.0, max(2.0, base + skew))
        ask_offset = min(60.0, max(2.0, base - skew))
        bid_size = 2 if inventory < 45 else 0
        ask_size = 2 if inventory > -45 else 0

        if "adverse-selection alert" in mandate:
            bid_size = min(bid_size, 1)
            ask_size = min(ask_size, 1)
            primary_mid = 0.5 * (float(asset["primary_bid"]) + float(asset["primary_ask"]))
            maker_bid_floor = 10_000.0 * (1.0 - float(asset["dual_ask"]) / primary_mid) + 0.25
            maker_ask_floor = 10_000.0 * (float(asset["dual_bid"]) / primary_mid - 1.0) + 0.25
            bid_offset = min(80.0, max(bid_offset, maker_bid_floor))
            ask_offset = min(80.0, max(ask_offset, maker_ask_floor))
        if "long-inventory recovery" in mandate:
            bid_size = 0 if "liquidity campaign" in mandate else min(bid_size, 1)
            ask_size = max(1, ask_size)
        if "short-inventory recovery" in mandate:
            ask_size = 0 if "liquidity campaign" in mandate else min(ask_size, 1)
            bid_size = max(1, bid_size)
        actions[symbol] = {
            "bid_offset_bps": bid_offset,
            "ask_offset_bps": ask_offset,
            "bid_size": bid_size,
            "ask_size": ask_size,
        }
    return actions
# EVOLVE-BLOCK-END
