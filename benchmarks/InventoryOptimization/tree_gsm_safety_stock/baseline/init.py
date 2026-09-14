# EVOLVE-BLOCK-START
"""Baseline implementation for Task 01.

This module intentionally avoids stockpyl and only contains a simple
rule-based CST assignment.

Contract
--------
This file runs as a *standalone program* in an isolated working directory.
The evaluator runs it in a subprocess and reads only ``submission.json``:

    {"cst": {"1": <int>, "2": <int>, "3": <int>, "4": <int>}}

JSON object keys are always strings, so the node ids are re-parsed as ints by
the evaluator. The evaluator recomputes every cost from this CST dict itself,
so nothing else this file could report would matter.
"""

from __future__ import annotations

import json
from pathlib import Path

PROCESSING_TIME = {
    1: 2.0,
    3: 1.0,
    2: 1.0,
    4: 1.0,
}


def solve() -> dict[int, int]:
    """Rule-based CST policy.

    Rule:
    - demand-facing nodes follow SLA directly
    - internal nodes use processing-time threshold
    """

    cst = {2: 0, 4: 1}
    for idx, processing_time in PROCESSING_TIME.items():
        if idx in cst:
            continue
        cst[idx] = 1 if float(processing_time) >= 2.0 else 0

    return cst


def _write_submission(cst: dict[int, int]) -> None:
    Path("submission.json").write_text(
        json.dumps({"cst": {str(k): int(v) for k, v in cst.items()}}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    _write_submission(solve())
# EVOLVE-BLOCK-END
