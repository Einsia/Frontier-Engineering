"""End-to-end regression for the joint_replenishment pilot conversion.

This task was the one a candidate could score 1.0 by reporting a negative base
cycle time (the archived exploit). The evaluator now runs the candidate in a
subprocess and validates its own inputs, so the honest baseline must still score
its published value and a negative-cycle submission must be rejected.

These run the *task's* verification/evaluate.py, not the harness; they exercise
the conversion directly and need no stockpyl for the candidate (the stockpyl
reference is imported but that is material to the scoring comparison only).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_DIR = REPO_ROOT / "benchmarks" / "InventoryOptimization" / "joint_replenishment"
EVALUATOR = TASK_DIR / "verification" / "evaluate.py"
CANDIDATE = TASK_DIR / "baseline" / "init.py"

HONEST = CANDIDATE.read_text(encoding="utf-8")

MALICIOUS_NEGATIVE_CYCLE = '''# EVOLVE-BLOCK-START
"""Malicious: negative base cycle time, writes submission.json."""
from __future__ import annotations
import json
import pathlib
def solve() -> dict:
    return {"base_cycle_time": -1.0, "order_multiples": [-1] * 8}
if __name__ == "__main__":
    pathlib.Path("submission.json").write_text(json.dumps(solve()), encoding="utf-8")
'''


def _run_evaluator() -> dict:
    proc = subprocess.run(
        [sys.executable, str(EVALUATOR)],
        cwd=str(TASK_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"evaluator crashed: {proc.stderr}"
    comparison = (TASK_DIR / "output" / "comparison.json").read_text(encoding="utf-8")
    return json.loads(comparison)


@pytest.fixture()
def restore_candidate():
    yield
    CANDIDATE.write_text(HONEST, encoding="utf-8")
    # Reset regenerated comparison artifacts so we never commit them.
    import subprocess as sp

    sp.run(
        ["git", "checkout", "--", str(TASK_DIR / "output")],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
    )


def test_honest_candidate_scores_published_value(restore_candidate) -> None:
    CANDIDATE.write_text(HONEST, encoding="utf-8")
    comparison = _run_evaluator()
    # Published baseline_final_score (matches the committed comparison.json).
    assert abs(comparison["baseline_final_score"] - 0.3034231848949367) < 1e-9


def test_negative_cycle_is_rejected(restore_candidate) -> None:
    CANDIDATE.write_text(MALICIOUS_NEGATIVE_CYCLE, encoding="utf-8")
    comparison = _run_evaluator()
    assert comparison["baseline_final_score"] == 0.0
    assert "positive" in comparison["candidate_error"]
