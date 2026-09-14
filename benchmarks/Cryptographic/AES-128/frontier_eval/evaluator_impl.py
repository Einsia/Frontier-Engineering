"""Task-local entrypoint for the shared Cryptographic scorer.

Scoring is implemented in ``benchmarks/_shared/crypto_eval.py``, outside the
benchmark directory copied into candidate workspaces. This module locates that
implementation and forwards the evaluation request.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "benchmarks" / "_shared" / "crypto_eval.py").is_file():
            return parent
    raise RuntimeError(
        "could not locate the repo root holding benchmarks/_shared/crypto_eval.py; "
        "set FRONTIER_ENGINEERING_ROOT"
    )


_SHARED = _find_repo_root() / "benchmarks" / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

# Imported at module load, i.e. long before any candidate binary exists. The
# reference implementations self-test against the published vectors on import;
# if that fails the scorer refuses to score rather than trusting the candidate.
from crypto_eval import evaluate as _evaluate  # noqa: E402


def evaluate(
    program_path: str,
    *,
    repo_root: Path | None = None,
    spec: Any,
    include_pdf_reference: bool = False,
) -> Any:
    return _evaluate(
        program_path,
        repo_root=repo_root,
        spec=spec,
        include_pdf_reference=include_pdf_reference,
    )
