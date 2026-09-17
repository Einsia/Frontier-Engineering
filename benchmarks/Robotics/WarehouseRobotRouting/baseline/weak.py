from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from verification.problem import solve_random  # noqa: E402


def solve(instance: dict[str, Any]) -> dict[str, Any]:
    return solve_random(instance)


if __name__ == "__main__":
    json.dump(solve(json.load(sys.stdin)), sys.stdout, allow_nan=False)
    sys.stdout.write("\n")
