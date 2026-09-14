"""Adapter for the shared Cryptographic scorer.

``benchmarks/_shared/crypto_eval.py`` implements scoring for all three tasks.
Return a metrics dictionary when ``openevolve`` is unavailable, or an
``EvaluationResult`` when it is installed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ..spec import CryptographicSpec

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SHARED = _REPO_ROOT / "benchmarks" / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

# Loaded here, at import time, so the scoring logic and its self-tested
# reference implementations are resident before any candidate is compiled.
from crypto_eval import evaluate as _evaluate  # noqa: E402


def evaluate(
    program_path: str,
    *,
    repo_root: Path | None = None,
    spec: CryptographicSpec,
    include_pdf_reference: bool = False,
) -> Any:
    result = _evaluate(
        program_path,
        repo_root=repo_root,
        spec=spec,
        include_pdf_reference=include_pdf_reference,
    )
    if isinstance(result, dict) and set(result) == {"metrics", "artifacts"}:
        # Match this entry point's historical contract: metrics only when
        # openevolve is unavailable.
        return result["metrics"]
    return result
