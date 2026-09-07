"""Task-local entry point for the Cryptographic scorer.

Deliberately thin. The scoring logic lives in ``benchmarks/_shared/crypto_eval.py``
so that it sits *outside* every benchmark directory: this task's
``copy_files.txt`` is ``.``, so anything kept under ``frontier_eval/`` here is
copied into the agent's workspace, and it is the workspace copy that
``run_eval.py`` actually executes. Keeping the scorer out of that tree means
there is no workspace copy of it to edit in the first place.

The previous implementation lived here in full (566 lines) and, among other
things, compiled ``verification/evaluate.cpp`` *after* the candidate binary had
already run with its cwd set to that same directory. See the module docstring of
``crypto_eval`` for the full list of what was wrong and what replaced it.
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
