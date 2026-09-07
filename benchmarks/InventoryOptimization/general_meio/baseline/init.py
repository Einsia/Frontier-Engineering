# EVOLVE-BLOCK-START
"""Baseline implementation for Task 02.

No stockpyl optimizer is used here.

Contract
--------
This file runs as a *standalone program* in an isolated working directory.
The evaluator runs it in a subprocess and reads only ``submission.json``:

    {"base_stock": {"10": <int>, "20": <int>, "30": <int>, "40": <int>, "50": <int>}}

JSON object keys are always strings, so node ids are re-parsed as ints by the
evaluator. The evaluator re-simulates the network from this policy itself, so
nothing else this file could report would matter.
"""

from __future__ import annotations

import json
from pathlib import Path


def solve() -> dict[int, int]:
    """Manual demand-coverage heuristic for base-stock levels."""

    mean_40 = 8.0
    mean_50 = 7.0
    sink_total = mean_40 + mean_50

    s40 = round(2.0 * mean_40)
    s50 = round(2.0 * mean_50)
    s20 = round(0.93 * sink_total)
    s30 = round(0.93 * sink_total)
    s10 = round(1.73 * sink_total)

    return {10: s10, 20: s20, 30: s30, 40: s40, 50: s50}


def _write_submission(base_stock: dict[int, int]) -> None:
    Path("submission.json").write_text(
        json.dumps({"base_stock": {str(k): int(v) for k, v in base_stock.items()}}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    _write_submission(solve())
# EVOLVE-BLOCK-END
