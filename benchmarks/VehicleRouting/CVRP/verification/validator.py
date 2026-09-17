"""Candidate integrity validator for the CVRP benchmark.

Enforces the task constraints as *executable* checks (not just natural
language). The evaluator runs these before scoring; any violation marks the
candidate invalid.

Checks implemented:
  1. EVOLVE-BLOCK integrity: markers must exist, and the code outside the
     EVOLVE-BLOCK region must match the initial baseline byte-for-byte.
  2. Forbidden references: the source must not reference the verification
     module, the reference solver, `reference.json`, or helper internals.
  3. Absolute paths: the source must not contain machine-local filesystem
     paths.
  4. Per-instance hardcoding: the source must not embed instance names in a
     solution-dispatch form (e.g. `"VRP-19-2": [...]`).
  5. Determinism: running the candidate twice on the same instance must yield
     byte-identical output (a scorer needs reproducible results).

Pure standard library. Used by `verification/evaluator.py` and
`frontier_eval/evaluator.py` (which embeds an equivalent copy for sandbox use).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

EVOLVE_START = "# EVOLVE-BLOCK-START"
EVOLVE_END = "# EVOLVE-BLOCK-END"

# Strong tokens: almost never appear in legitimate solver code, so a bare
# substring match is fine (e.g. "ref_solver", "reference.json").
STRONG_TOKENS = (
    "ref_solver",
    "grasp_solve",
    "savings_solve",
    "reference.json",
)
# Weak token "verification": only rejected when it appears in an
# import/from/module-path context, so a comment like "verification pass"
# is NOT a false positive.
FORBIDDEN_RE = (
    re.compile(r"\b(?:import|from)\s+verification\b"),
    re.compile(r"verification[\\/.]"),
)

# e.g. `"VRP-19-2": [...]` or `"VHO-22-3":` (a dispatch table keyed by name).
HARDCODE_RE = re.compile(r"[\"'][A-Z][A-Z0-9-]*\d+-\d+[\"']\s*:")
# Windows drive / POSIX home absolute paths.
ABS_PATH_RE = re.compile(r"[A-Za-z]:[\\/]|/home/|/Users/")


def split_evolve_blocks(src: str) -> tuple[str, str, str] | None:
    """Return (before_start, between, after_end) or None if markers missing."""
    start = src.find(EVOLVE_START)
    end = src.find(EVOLVE_END)
    if start == -1 or end == -1 or end <= start:
        return None
    return (
        src[:start],
        src[start + len(EVOLVE_START) : end],
        src[end + len(EVOLVE_END) :],
    )


def fixed_region(parts: tuple[str, str, str]) -> str:
    """Everything outside the EVOLVE-BLOCK (the read-only part)."""
    return parts[0] + parts[2]


def static_check_source(src: str, baseline_src: str | None = None) -> list[str]:
    """Static checks on candidate source text. Returns a list of violations."""
    issues: list[str] = []

    parts = split_evolve_blocks(src)
    if parts is None:
        issues.append("missing EVOLVE-BLOCK-START / EVOLVE-BLOCK-END markers")
    elif baseline_src is not None:
        init_parts = split_evolve_blocks(baseline_src)
        if init_parts is not None and fixed_region(init_parts) != fixed_region(parts):
            issues.append("code outside EVOLVE-BLOCK differs from initial baseline")

    for token in STRONG_TOKENS:
        if token in src:
            issues.append(f"candidate references forbidden token {token!r}")
    for pat in FORBIDDEN_RE:
        if pat.search(src):
            issues.append("candidate references forbidden token 'verification'")

    if ABS_PATH_RE.search(src):
        issues.append("candidate contains an absolute filesystem path")

    if HARDCODE_RE.search(src):
        issues.append("candidate hardcodes per-instance solutions by name")

    return issues


def check_candidate(
    solver_path: Path | str, baseline_path: Path | str | None = None
) -> list[str]:
    """Read candidate source and run the static checks.

    `baseline_path` is the pristine initial program used to verify the fixed
    (non-EVOLVE-BLOCK) region. When None, the EVOLVE-BLOCK marker check still
    applies but the fixed-region diff is skipped.
    """
    solver_path = Path(solver_path)
    try:
        src = solver_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return [f"cannot read candidate source: {exc}"]

    baseline_src = None
    if baseline_path is not None:
        try:
            baseline_src = Path(baseline_path).read_text(
                encoding="utf-8", errors="replace"
            )
        except Exception:
            baseline_src = None

    return static_check_source(src, baseline_src)


def candidate_env() -> dict[str, str]:
    """Environment for the candidate subprocess, stripped of host paths and any
    reference-distance settings so the candidate cannot locate the scoring
    baseline on the host. All `FRONTIER_*` variables are removed (the unified
    runtime sets `FRONTIER_ENGINEERING_ROOT` to the repo root, which would
    otherwise let a candidate find and import `verification/ref_solver.py` on
    the host)."""
    env = os.environ.copy()
    for key in list(env):
        upper = key.upper()
        if upper.startswith("FRONTIER") or key in (
            "CVRP_EVAL_REFERENCE_JSON",
            "CVRP_EVAL_REFERENCES",
        ):
            del env[key]
    return env


def check_determinism(
    python: str,
    solver_path: Path | str,
    inst_path: Path | str,
    timeout: float,
    env: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """Run the candidate twice on the same instance; outputs must match.

    Returns (ok, note). A non-deterministic candidate is not reliably
    scoreable, so it is treated as a violation.
    """
    solver_path = Path(solver_path)
    inst_path = Path(inst_path)
    outputs: list[Any] = []
    for _ in range(2):
        with tempfile.TemporaryDirectory(prefix="cvrp_det_") as td:
            out_path = Path(td) / "out.json"
            try:
                proc = subprocess.run(
                    [python, str(solver_path), str(inst_path), str(out_path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(solver_path.parent),
                    env=env if env is not None else candidate_env(),
                )
            except subprocess.TimeoutExpired:
                return False, "timeout during determinism check"
            if proc.returncode != 0:
                return (
                    False,
                    f"candidate exited with code {proc.returncode} during "
                    f"determinism check: {(proc.stderr or '')[:200]}",
                )
            try:
                outputs.append(json.loads(out_path.read_text(encoding="utf-8")))
            except Exception as exc:
                return False, f"cannot parse determinism output: {exc}"
    if outputs[0] != outputs[1]:
        return False, "candidate is not deterministic (output differs across two runs)"
    return True, ""


def select_determinism_probes(
    inst_paths: list, parse_instance, count: int = 3
) -> list:
    """Pick min / median / max instances (by customer count) as determinism
    probes, so a solver that is deterministic on small instances but random on
    large ones cannot slip through a single-probe check."""
    parsed = sorted(
        ((p, parse_instance(p)) for p in inst_paths), key=lambda t: t[1]["n"]
    )
    if not parsed:
        return []
    idxs = sorted({0, len(parsed) // 2, len(parsed) - 1})
    return [parsed[i][0] for i in idxs[:count]]
