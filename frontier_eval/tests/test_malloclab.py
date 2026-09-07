"""MallocLab: the score must not travel over a channel the candidate owns.

mm.c is compiled into mdriver, so unlike every other benchmark here the
candidate cannot be moved out of the scoring process -- the allocator has to
live in the address space whose allocations are being measured. What can be
fixed is the *channel*: the score used to be scraped from mdriver's stdout,
which mm.c can print to.

These tests are slow (each one runs `make` and replays 11 traces), so they are
marked and skipped without a compiler.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_DIR = REPO_ROOT / "benchmarks" / "ComputerSystems" / "MallocLab"
HONEST_SCORE = 28.145173

pytestmark = pytest.mark.skipif(
    shutil.which("gcc") is None or shutil.which("make") is None,
    reason="MallocLab needs gcc and make",
)

# Prints a perfect Score line after mdriver prints the real one. The old parser
# took the *last* matching line in stdout, so this alone was 100/100.
STDOUT_SPOOF = """
#include <stdio.h>
#include <stdlib.h>
static void shout(void) {
  printf("Score = (60 (util) + 40 (thru)) * 11/11 (testcase) = 100/100\\n");
  fflush(stdout);
}
__attribute__((constructor)) static void arm(void) { atexit(shout); }
"""

# Reads the run token off stdin before main() gets it.
TOKEN_THEFT = """
#include <stdio.h>
static char stolen[256];
__attribute__((constructor)) static void steal(void) {
  (void)!fgets(stolen, sizeof(stolen), stdin);
}
"""


def _run(workdir: Path) -> dict:
    subprocess.run(
        ["bash", "frontier_eval/run_eval.sh", sys.executable, str(workdir), "malloclab-handout/mm.c"],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        timeout=900,
        check=True,
    )
    return json.loads((workdir / "metrics.json").read_text(encoding="utf-8"))


@pytest.fixture()
def bench(tmp_path_factory):
    """A throwaway copy of the benchmark; never mutates the repo tree."""
    work = Path(tempfile.mkdtemp(dir=tmp_path_factory.mktemp("malloclab"))) / "bench"
    shutil.copytree(TASK_DIR, work)
    return work


def _append_to_mm(workdir: Path, source: str) -> None:
    mm = workdir / "malloclab-handout" / "mm.c"
    mm.write_text(mm.read_text(encoding="utf-8") + source, encoding="utf-8")


def test_honest_baseline_scores_its_published_value(bench) -> None:
    metrics = _run(bench)
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == pytest.approx(HONEST_SCORE, abs=1e-6)
    # 6 of 11 traces pass; mdriver already prices that in. A failing trace is a
    # low score, not an invalid run.
    assert metrics["testcases_passed"] == 6.0
    assert metrics["errors"] == 5.0


def test_printing_a_perfect_score_no_longer_works(bench) -> None:
    _append_to_mm(bench, STDOUT_SPOOF)
    metrics = _run(bench)
    assert metrics["combined_score"] == pytest.approx(HONEST_SCORE, abs=1e-6)
    # The spoof really did run -- this asserts the parser ignored it, not that
    # the exploit failed to fire.
    stdout = (bench / "mdriver.stdout.txt").read_text(encoding="utf-8")
    assert "= 100/100" in stdout


def test_the_old_parser_would_have_been_fooled(bench) -> None:
    """Guards against the test above passing for the wrong reason."""
    _append_to_mm(bench, STDOUT_SPOOF)
    _run(bench)
    stdout = (bench / "mdriver.stdout.txt").read_text(encoding="utf-8")
    old = subprocess.run(
        ["git", "show", "HEAD:benchmarks/ComputerSystems/MallocLab/frontier_eval/parse_mdriver_result.py"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if old.returncode != 0:
        pytest.skip("pre-fix parser not reachable from git")
    if "--expected-token" in old.stdout:
        pytest.skip("HEAD already contains the fix")
    parser = bench / "old_parser.py"
    parser.write_text(old.stdout, encoding="utf-8")
    out = bench / "old_metrics.json"
    subprocess.run(
        [sys.executable, str(parser), "--stdout-file", str(bench / "mdriver.stdout.txt"),
         "--stderr-file", str(bench / "mdriver.stderr.txt"),
         "--mdriver-returncode", "0", "--metrics-out", str(out)],
        check=True, capture_output=True, timeout=60,
    )
    assert json.loads(out.read_text(encoding="utf-8"))["combined_score"] == 100.0


def test_stealing_the_token_before_main_fails_loudly(bench) -> None:
    """A candidate that eats stdin gets a zero, not a silent pass."""
    _append_to_mm(bench, TOKEN_THEFT)
    metrics = _run(bench)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == 0.0
    assert metrics["mdriver_returncode"] == 2.0
    assert "no result record" in metrics["error_message"]


@pytest.mark.xfail(
    reason=(
        "KNOWN AND UNFIXED. mm.c is linked into mdriver, so a candidate that "
        "steals the token pre-main, replays it onto fd 0 with dup2 so main() "
        "still starts, reads the -o path out of /proc/self/cmdline and forges "
        "the record from an atexit handler scores 100. Verified, not assumed. "
        "Closing this needs the allocator out of the grading process, which "
        "the benchmark's premise does not allow -- see README."
    ),
    strict=True,
)
def test_token_replay_forgery_is_still_possible(bench) -> None:
    _append_to_mm(bench, (TASK_DIR / "frontier_eval" / "known_exploit_token_replay.c").read_text())
    assert _run(bench)["combined_score"] == pytest.approx(HONEST_SCORE, abs=1e-6)
