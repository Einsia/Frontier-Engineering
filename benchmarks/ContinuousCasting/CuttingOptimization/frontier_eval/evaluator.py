"""Unified evaluator entry point for the CuttingOptimization benchmark.

This module is loaded by `frontier_eval/run_eval.py` and must expose a
top-level `evaluate(program_path, **kwargs)` callable. The real
implementation lives in `verification/evaluate.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

TIME_BUDGET_S = 60.0


def _load_verification_evaluator() -> Any:
    evaluator_path = (
        Path(__file__).resolve().parent.parent / "verification" / "evaluate.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_cutting_verification_evaluator", evaluator_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load verification evaluator from {evaluator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(program_path: str, **kwargs: Any) -> Any:
    module = _load_verification_evaluator()
    result = module.evaluate(program_path, time_budget=TIME_BUDGET_S, **kwargs)
    if isinstance(result, dict) and "metrics" in result:
        return result
    return {"metrics": result, "artifacts": {}}
