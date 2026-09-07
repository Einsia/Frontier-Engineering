"""The sampler driver's clock must not be reachable by the candidate.

sampler_isolation.py runs the candidate with runpy.run_path *inside* the driver
process -- that is the design: the driver is the sandbox, and the scoring
process is elsewhere. But it also timed each repeat there with `time.time()`,
which Python resolves on the module object at call time. A candidate doing
`import time; time.time = lambda: 0.0` made every repeat report 0.0s. On
HighReliableSimulation, whose score is T0/(runtime_median * err_log_ratio),
that was worth about 39600x the honest score.

Two defences, tested here:
  * the driver binds the clock to a local before the candidate is executed, so
    rebinding the module attribute does nothing;
  * the parent bounds the self-reported total by the wall clock it measured
    itself, which the child cannot touch at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED = REPO_ROOT / "benchmarks" / "_shared"
sys.path.insert(0, str(SHARED))

import sampler_isolation as si  # noqa: E402


def test_driver_binds_the_clock_before_running_the_candidate() -> None:
    """Ordering is the whole defence, so assert on the order, not on a name."""
    src = si._DRIVER_SOURCE
    bind = src.index("_clock = time.monotonic")
    run = src.index("runpy.run_path(")
    assert bind < run, "the clock must be captured before the candidate exists"
    # And nothing in the timed region may go back through the module.
    timed = src[src.index("t0 = _clock()") : src.index("dt = _clock() - t0")]
    assert "time.time" not in timed and "time.monotonic" not in timed


def test_rebinding_time_time_does_not_change_a_captured_local() -> None:
    """The language-level reason the fix works, pinned so it cannot regress."""
    import time

    captured = time.monotonic
    original = time.time
    try:
        time.time = lambda: 0.0
        assert time.time() == 0.0  # the old code would have read this
        assert captured() > 0.0  # the new code reads this
    finally:
        time.time = original


class _Run:
    """Minimal stand-in for candidate_sandbox.IsolatedRun."""

    def __init__(self, runtime_s: float) -> None:
        self.runtime_s = runtime_s


def _records(*runtimes: float) -> list[dict]:
    return [
        {"repeat": i, "runtime_s": v, "raw": {}, "audit": {}}
        for i, v in enumerate(runtimes)
    ]


@pytest.mark.parametrize(
    "reported, wall, ok",
    [
        ([9.0, 9.0], 20.0, True),      # honest: most of the wall clock
        ([0.0, 0.0], 20.0, False),     # the exploit: report nothing
        ([1e-9, 1e-9], 20.0, False),   # the exploit, less blatantly
        ([500.0], 20.0, False),        # claiming more than it was alive
        ([0.4, 0.4], 2.0, True),       # short run: the floor must not fire
    ],
)
def test_wall_clock_bounds_the_self_reported_total(reported, wall, ok) -> None:
    total = sum(reported)
    slack = si.WALL_CLOCK_SLACK_S
    floor = si.WALL_CLOCK_MIN_FRACTION * (wall - si.WALL_CLOCK_STARTUP_S)
    too_high = total > wall + slack
    too_low = floor > 0.0 and total < floor
    assert (not (too_high or too_low)) is ok, (
        f"reported={total} wall={wall} floor={floor} slack={slack}"
    )
