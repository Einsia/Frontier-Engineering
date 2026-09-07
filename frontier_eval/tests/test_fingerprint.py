"""Tests for the unified evaluator's readonly-fingerprint machinery.

These functions are the only thing standing between a candidate program and
silent tampering with the scorer's own source tree, and until now they had no
test coverage at all.

Two groups of tests live here:

* ``TestCurrentBehaviour`` locks in behaviour that must survive any hardening
  work -- real edits are caught, directory entries are walked, and the ``"."``
  whole-benchmark form keeps working.
* ``TestHardening`` states the behaviour we *want*: bytecode caches must not be
  a blind spot, and a ``readonly_files.txt`` entry must not be able to point
  outside the sandbox.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from frontier_eval.tasks.unified.evaluator.python import (  # noqa: E402
    _check_readonly_violations,
    _fingerprint_path,
    _snapshot_readonly,
)


@pytest.fixture()
def benchmark(tmp_path: Path) -> Path:
    """A miniature stand-in for a sandboxed benchmark directory."""
    root = tmp_path / "benchmark"
    (root / "verification").mkdir(parents=True)
    (root / "verification" / "evaluator.py").write_text("def score():\n    return 1.0\n")
    (root / "verification" / "reference.py").write_text("SOLUTION = 42\n")
    (root / "baseline").mkdir()
    (root / "baseline" / "init.py").write_text("def solve():\n    return 0\n")
    (root / "README.md").write_text("# task\n")
    return root


class TestCurrentBehaviour:
    """Behaviour that hardening must not regress."""

    def test_untouched_tree_reports_no_violation(self, benchmark: Path) -> None:
        before = _snapshot_readonly(benchmark, ("verification", "README.md"))
        assert _check_readonly_violations(benchmark, before) == []

    def test_edited_file_is_caught(self, benchmark: Path) -> None:
        before = _snapshot_readonly(benchmark, ("verification",))
        (benchmark / "verification" / "evaluator.py").write_text("def score():\n    return 99.0\n")
        assert _check_readonly_violations(benchmark, before) == ["verification"]

    def test_added_file_in_readonly_dir_is_caught(self, benchmark: Path) -> None:
        before = _snapshot_readonly(benchmark, ("verification",))
        (benchmark / "verification" / "sneaky.py").write_text("x = 1\n")
        assert _check_readonly_violations(benchmark, before) == ["verification"]

    def test_deleted_file_is_caught(self, benchmark: Path) -> None:
        before = _snapshot_readonly(benchmark, ("verification",))
        (benchmark / "verification" / "reference.py").unlink()
        assert _check_readonly_violations(benchmark, before) == ["verification"]

    def test_writes_outside_readonly_paths_are_allowed(self, benchmark: Path) -> None:
        """Candidates legitimately write to their own destination."""
        before = _snapshot_readonly(benchmark, ("verification",))
        (benchmark / "baseline" / "init.py").write_text("def solve():\n    return 7\n")
        (benchmark / "metrics.json").write_text("{}\n")
        assert _check_readonly_violations(benchmark, before) == []

    def test_dot_covers_whole_benchmark(self, benchmark: Path) -> None:
        before = _snapshot_readonly(benchmark, (".",))
        (benchmark / "baseline" / "init.py").write_text("tampered\n")
        assert _check_readonly_violations(benchmark, before) == ["."]

    def test_missing_target_is_stable(self, benchmark: Path) -> None:
        before = _snapshot_readonly(benchmark, ("does_not_exist",))
        assert before["does_not_exist"] == "__MISSING__"
        assert _check_readonly_violations(benchmark, before) == []

    def test_creating_a_previously_missing_target_is_caught(self, benchmark: Path) -> None:
        before = _snapshot_readonly(benchmark, ("verification/injected.py",))
        (benchmark / "verification" / "injected.py").write_text("x = 1\n")
        assert _check_readonly_violations(benchmark, before) == ["verification/injected.py"]


class TestHardening:
    """Behaviour we want after closing the bytecode and path-escape holes."""

    def test_stale_bytecode_is_not_a_blind_spot(self, benchmark: Path) -> None:
        """A poisoned .pyc shadows its .py at import time, so it must be fingerprinted.

        CPython prefers a cached ``.pyc`` whose header still matches the source's
        mtime and size, which makes ``__pycache__`` a place to hide a rewritten
        scorer without touching any ``.py`` file.
        """
        before = _snapshot_readonly(benchmark, ("verification",))
        cache = benchmark / "verification" / "__pycache__"
        cache.mkdir()
        (cache / "evaluator.cpython-312.pyc").write_bytes(b"\x00poisoned bytecode\x00")
        assert _check_readonly_violations(benchmark, before) == ["verification"]

    def test_bytecode_written_next_to_a_readonly_file_is_caught(self, benchmark: Path) -> None:
        before = _snapshot_readonly(benchmark, (".",))
        cache = benchmark / "baseline" / "__pycache__"
        cache.mkdir()
        (cache / "init.cpython-312.pyc").write_bytes(b"\x00poisoned\x00")
        assert _check_readonly_violations(benchmark, before) == ["."]

    def test_readonly_entry_cannot_escape_the_sandbox(self, benchmark: Path) -> None:
        """``readonly_files.txt`` is task-supplied data and must stay in-bounds."""
        outside = benchmark.parent / "outside.txt"
        outside.write_text("secret\n")
        snapshot = _snapshot_readonly(benchmark, ("../outside.txt",))
        assert snapshot["../outside.txt"] == "__OUT_OF_BOUNDS__"

    def test_absolute_readonly_entry_is_rejected(self, benchmark: Path) -> None:
        snapshot = _snapshot_readonly(benchmark, ("/etc/hostname",))
        assert snapshot["/etc/hostname"] == "__OUT_OF_BOUNDS__"


class TestFingerprintPrimitives:
    def test_file_and_dir_fingerprints_are_tagged(self, benchmark: Path) -> None:
        assert _fingerprint_path(benchmark / "README.md").startswith("file:")
        assert _fingerprint_path(benchmark / "verification").startswith("dir:")

    def test_fingerprint_is_content_addressed_not_path_addressed(self, benchmark: Path) -> None:
        same = benchmark / "verification" / "copy.py"
        same.write_text((benchmark / "verification" / "reference.py").read_text())
        assert _fingerprint_path(same) == _fingerprint_path(benchmark / "verification" / "reference.py")
