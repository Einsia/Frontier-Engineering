"""Unified evaluator entry point for the TelecomBackup benchmark.

This module is loaded by `frontier_eval/run_eval.py` and must expose a
top-level `evaluate(program_path, **kwargs)` callable. The real
implementation lives in `verification/evaluate.py`.

The per-instance solve budget is deliberately *not* hard-coded here: it is
resolved from ``TELECOM_EVAL_TIME_BUDGET`` (the 300 / 60 / 10 s budget tiers
documented in the README); the default is the 60 s "advanced" tier.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

DEFAULT_TIME_BUDGET_S = 60.0


def _time_budget_s() -> float:
    """Per-instance solve budget (s); override with TELECOM_EVAL_TIME_BUDGET."""
    raw = os.environ.get("TELECOM_EVAL_TIME_BUDGET", "").strip()
    if not raw:
        return DEFAULT_TIME_BUDGET_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIME_BUDGET_S
    return value if value > 0 else DEFAULT_TIME_BUDGET_S


def _load_verification_evaluator() -> Any:
    evaluator_path = (
        Path(__file__).resolve().parent.parent / "verification" / "evaluate.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_telecombackup_verification_evaluator", evaluator_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load verification evaluator from {evaluator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(program_path: str, **kwargs: Any) -> Any:
    module = _load_verification_evaluator()
    result = module.evaluate(program_path, time_budget=_time_budget_s(), **kwargs)
    if isinstance(result, dict) and "metrics" in result:
        return result
    return {"metrics": result, "artifacts": {}}
