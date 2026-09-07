"""Isolation regression for the four ``Optics/adaptive_*`` evaluators.

These tasks used to ``exec_module`` the candidate into the scoring interpreter
and call its function once per simulation step. They now launch the candidate as
its own process, hand it only the observations (never the ground-truth phase),
and recompute every metric -- and the final score -- in the scorer.

Properties enforced here, per task:

* **Honest candidate, unchanged score.** The committed baseline, run through the
  new subprocess contract, must reproduce the pre-conversion score bit for bit.
  This also proves the committed ``baseline/init.py`` really is a standalone
  script that emits ``submission.npz``.
* **Invalid output is rejected.** Crash, no output, wrong shape, self-reported
  score, out-of-bounds commands and non-finite commands must all be hard
  rejections: evaluator exits non-zero, writes no ``metrics.json``, and records
  the reason. That is what ``frontier_eval/tasks/.../parse_result.py`` turns into
  ``valid = 0`` / ``combined_score = -1e18``.
* **No ground truth leaks.** ``problem.npz`` must carry observations only; the
  phase the score is computed against must never reach the candidate.

Malicious candidates are passed via ``--candidate``; the repository's own
``baseline/init.py`` files are never written to.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPTICS = REPO_ROOT / "benchmarks" / "Optics"
PY = "/usr/bin/python3.12"

# Pre-conversion published scores, captured by running the original in-process
# evaluators at their default settings. The conversion must not move them.
EXPECTED_BASELINE_SCORE = {
    "adaptive_constrained_dm_control": 0.20516512992698066,
    "adaptive_temporal_smooth_control": 0.31517132841504814,
    "adaptive_energy_aware_control": 0.186257597230776,
    "adaptive_fault_tolerant_fusion": 0.3958695233765083,
}
EXPECTED_REFERENCE_SCORE = {
    "adaptive_constrained_dm_control": 0.7435991669679822,
    "adaptive_temporal_smooth_control": 0.6510199758125246,
    "adaptive_energy_aware_control": 0.6270277662865029,
    "adaptive_fault_tolerant_fusion": 0.6397691062040366,
}

TASKS = sorted(EXPECTED_BASELINE_SCORE)

# Flags that shrink a run for the rejection tests, where the score is irrelevant
# and only the reject path matters.
SMALL_RUN = {
    "adaptive_constrained_dm_control": ["--cases", "4"],
    "adaptive_energy_aware_control": ["--cases", "4"],
    "adaptive_fault_tolerant_fusion": ["--cases", "4"],
    "adaptive_temporal_smooth_control": ["--episodes", "2", "--steps", "3"],
}

# --------------------------------------------------------------------------- #
# Malicious / broken candidates. Each is a complete standalone script.
# --------------------------------------------------------------------------- #

# Reports a fabricated score and a token command matrix of the wrong shape.
# Both the bogus "score" key and the shape must be caught.
MALICIOUS_SELF_REPORTED_SCORE = '''
import numpy as np
np.savez(
    "submission.npz",
    commands=np.zeros((1, 3)),
    score=1.0,
    score_0_to_1_higher_is_better=1.0,
    combined_score=1e9,
)
'''

# Right shape, but every actuator slammed far past the voltage bound.
MALICIOUS_OUT_OF_BOUNDS = '''
import numpy as np
data = np.load("problem.npz")
key = "slopes" if "slopes" in data.files else "slopes_multi"
n = data[key].shape[0]
n_act = int(data["n_act"])
np.savez("submission.npz", commands=np.full((n, n_act), 999.0))
'''

# Right shape and in bounds, but poisoned with NaN.
MALICIOUS_NON_FINITE = '''
import numpy as np
data = np.load("problem.npz")
key = "slopes" if "slopes" in data.files else "slopes_multi"
n = data[key].shape[0]
n_act = int(data["n_act"])
arr = np.zeros((n, n_act))
arr[0, 0] = np.nan
np.savez("submission.npz", commands=arr)
'''

# Crashes without producing anything.
MALICIOUS_CRASH = '''
import sys
sys.exit(1)
'''

# Exits cleanly but writes no submission at all.
MALICIOUS_NO_OUTPUT = '''
print("done, but produced nothing")
'''

# Imports a task's evaluator in-process and prints exactly which arrays
# ``build_problem`` would stage into the candidate's directory.
PROBLEM_KEY_PROBE = '''
import inspect
import json
import sys

sys.path.insert(0, sys.argv[1])
import evaluate as ev

cfg = ev.make_system()
if "episodes" in inspect.signature(ev.make_scenario).parameters:
    scenario = ev.make_scenario(cfg, 2, 2)
else:
    scenario = ev.make_scenario(cfg, 2)
problem = ev.build_problem(cfg, scenario, 0.15)
print(json.dumps(sorted(problem)))
'''

REJECTION_CASES = [
    ("self_reported_score", MALICIOUS_SELF_REPORTED_SCORE),
    ("out_of_bounds", MALICIOUS_OUT_OF_BOUNDS),
    ("non_finite", MALICIOUS_NON_FINITE),
    ("crash", MALICIOUS_CRASH),
    ("no_output", MALICIOUS_NO_OUTPUT),
]

# Any of these appearing as a problem.npz key would mean the scorer handed the
# candidate the answer it is graded against.
FORBIDDEN_KEY_SUBSTRINGS = ("phase", "coeff", "residual", "strehl", "rms", "plant_gain", "zern")


def _evaluate_py(task: str) -> Path:
    return OPTICS / task / "verification" / "evaluate.py"


def _run_evaluator(task: str, out_dir: Path, extra: list[str]) -> subprocess.CompletedProcess:
    """Run a task's verification/evaluate.py the way run_eval.sh does."""
    env = dict(os.environ)
    env["MPLBACKEND"] = "Agg"
    env["FRONTIER_ENGINEERING_ROOT"] = str(REPO_ROOT)
    return subprocess.run(
        [PY, str(_evaluate_py(task)), "--output-dir", str(out_dir), *extra],
        cwd=str(OPTICS / task),
        capture_output=True,
        text=True,
        timeout=900,
        env=env,
    )


def _write_candidate(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "candidate.py"
    path.write_text(source, encoding="utf-8")
    return path


@pytest.mark.parametrize("task", TASKS)
def test_honest_candidate_score_unchanged(task, tmp_path) -> None:
    """The committed baseline still scores exactly what it scored in-process.

    Runs with no ``--candidate`` override, so this also asserts the committed
    ``baseline/init.py`` is a working standalone script under the new contract.
    """
    out_dir = tmp_path / "out"
    proc = _run_evaluator(task, out_dir, [])
    assert proc.returncode == 0, f"evaluator failed: {proc.stderr[-3000:]}"

    payload = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    assert payload["candidate_execution"] == "isolated_subprocess"

    got = payload["baseline"]["score_0_to_1_higher_is_better"]
    assert got == EXPECTED_BASELINE_SCORE[task], f"{task}: baseline score drifted -> {got!r}"

    # The reference oracle still runs in-process; it must be untouched too.
    ref = payload["reference"]["score_0_to_1_higher_is_better"]
    assert ref == EXPECTED_REFERENCE_SCORE[task], f"{task}: reference score drifted -> {ref!r}"


@pytest.mark.parametrize("task", TASKS)
@pytest.mark.parametrize("label,source", REJECTION_CASES, ids=[c[0] for c in REJECTION_CASES])
def test_invalid_candidate_is_rejected(task, label, source, tmp_path) -> None:
    """Every bad-output mode is a hard rejection, not a degraded score."""
    out_dir = tmp_path / "out"
    candidate = _write_candidate(tmp_path, source)
    proc = _run_evaluator(task, out_dir, ["--candidate", str(candidate), *SMALL_RUN[task]])

    assert proc.returncode != 0, f"{task}/{label}: rejected candidate must exit non-zero"
    assert not (out_dir / "metrics.json").exists(), (
        f"{task}/{label}: a rejected run must not leave metrics.json behind, "
        "or the harness would score it"
    )

    rejection = json.loads((out_dir / "candidate_rejected.json").read_text(encoding="utf-8"))
    assert rejection["valid"] == 0.0
    assert rejection["combined_score"] == -1e18
    assert rejection["candidate_error"], "rejection must record a reason"


@pytest.mark.parametrize("task", TASKS)
def test_bounds_violation_is_named_in_rejection(task, tmp_path) -> None:
    """Bound checking is done by the scorer, not inherited from the candidate."""
    out_dir = tmp_path / "out"
    candidate = _write_candidate(tmp_path, MALICIOUS_OUT_OF_BOUNDS)
    _run_evaluator(task, out_dir, ["--candidate", str(candidate), *SMALL_RUN[task]])

    rejection = json.loads((out_dir / "candidate_rejected.json").read_text(encoding="utf-8"))
    assert "voltage bounds" in rejection["candidate_error"], rejection["candidate_error"]


@pytest.mark.parametrize("task", TASKS)
def test_candidate_never_receives_ground_truth(task, tmp_path) -> None:
    """``problem.npz`` carries observations only -- never the scored phase.

    Asks the evaluator itself what it would stage, rather than inferring it from
    a candidate's behaviour, so the assertion covers the real contract.
    """
    probe = tmp_path / "probe.py"
    probe.write_text(PROBLEM_KEY_PROBE, encoding="utf-8")
    env = dict(os.environ)
    env["MPLBACKEND"] = "Agg"
    env["FRONTIER_ENGINEERING_ROOT"] = str(REPO_ROOT)
    proc = subprocess.run(
        [PY, str(probe), str(OPTICS / task / "verification")],
        cwd=str(OPTICS / task),
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    assert proc.returncode == 0, f"probe failed: {proc.stderr[-3000:]}"

    keys = json.loads(proc.stdout.strip().splitlines()[-1])
    assert keys, "candidate would see no inputs at all"
    # The observations the controller is entitled to must actually be there.
    assert any(k in ("slopes", "slopes_multi") for k in keys), keys
    for key in keys:
        lowered = key.lower()
        for forbidden in FORBIDDEN_KEY_SUBSTRINGS:
            assert forbidden not in lowered, f"{task}: '{key}' leaks ground truth to the candidate"
