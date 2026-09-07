"""Shared pytest configuration for the frontier_eval test suite."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: end-to-end evaluator runs that drive a real simulator (tens of seconds)",
    )


def _dirty_benchmark_files() -> list[str]:
    """Tracked files under benchmarks/ that this session left modified."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--", "benchmarks"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    dirty = []
    for line in proc.stdout.splitlines():
        # Porcelain v1: two status columns, a space, then the path. Splitting
        # on the first space would keep the status letter in the path, since
        # an unstaged modification starts with a space (" M path").
        if len(line) < 4:
            continue
        status, path = line[:2], line[3:].strip()
        # Only tracked modifications; untracked build debris is not our concern.
        if status.strip() in {"M", "MM", "AM"}:
            dirty.append(path)
    return dirty


def pytest_sessionstart(session):
    """Record what was already dirty, so we only report what we caused."""
    session.config._fe_dirty_at_start = set(_dirty_benchmark_files())


def pytest_sessionfinish(session, exitstatus):
    """Warn loudly if the suite left a candidate behind in the repo.

    Several tests write attack candidates straight into the benchmark tree
    (TaskEnv in test_inventory_optimization.py, for one) and rely on a
    ``finally`` to put the honest source back. Any hard interruption -- Ctrl-C,
    a kill, an OOM, a CI timeout -- skips that, and what is left sitting in a
    *tracked* source file is a working exploit. Committing one as a shipped
    baseline is a genuinely bad outcome, so say so on the way out.
    """
    before = getattr(session.config, "_fe_dirty_at_start", set())
    leaked = [p for p in _dirty_benchmark_files() if p not in before]
    if not leaked:
        return
    writer = getattr(session.config, "get_terminal_writer", lambda: None)()
    message = (
        "\nTHIS SUITE LEFT TRACKED BENCHMARK FILES MODIFIED:\n"
        + "".join(f"  {p}\n" for p in leaked)
        + "These tests write candidate programs into the real tree and restore\n"
        "them in a finally block, so an interrupted run can leave an attack\n"
        "candidate in place. Inspect and restore before committing:\n"
        f"  git -C {REPO_ROOT} checkout -- " + " ".join(leaked) + "\n"
    )
    if writer is not None:
        writer.line(message, red=True, bold=True)
    else:
        print(message)
