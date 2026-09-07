from __future__ import annotations

import inspect
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

# Invariant 1 (benchmarks/_shared/candidate_sandbox.py): the scoring code must
# be resident in this process before any candidate code runs. The verification
# module used to be loaded inside evaluate(); it is now loaded at *import* time,
# which the harness reaches long before the candidate subprocess is spawned.
# Loading it later would mean re-reading a file the candidate shares a
# filesystem with.
#
# What is exec_module'd here is the benchmark's own scorer, never the
# candidate. The candidate only ever runs as a separate process and hands back
# a submission.json.
sys.dont_write_bytecode = True


def _load_verification_module() -> Any:
    evaluator_path = (
        Path(__file__).resolve().parents[1] / "verification" / "evaluator.py"
    ).resolve()
    spec = spec_from_file_location("_frontier_eval_verification_evaluator", evaluator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load verification evaluator from {evaluator_path}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_VERIFICATION = _load_verification_module()
_VERIFICATION_EVALUATE = getattr(_VERIFICATION, "evaluate")


def evaluate(program_path: str, *, repo_root: Path | None = None) -> Any:
    kwargs: dict[str, Any] = {}
    if (
        "repo_root" in inspect.signature(_VERIFICATION_EVALUATE).parameters
        and repo_root is not None
    ):
        kwargs["repo_root"] = repo_root
    return _VERIFICATION_EVALUATE(program_path, **kwargs)
