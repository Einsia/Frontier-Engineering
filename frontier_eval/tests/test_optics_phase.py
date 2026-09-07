"""Regression tests for the four Optics ``phase_*`` scoring contracts.

Before the isolation rework these four validators asked the *candidate* for the
problem, for the forward model and for the metrics::

    problem      = baseline_module.build_problem()
    baseline_sol = baseline_module.solve_baseline(problem)
    metrics_base = baseline_sol["metrics"]      # self-reported

Two archived exploits are reproduced here as tests:

* ``phase_dammann_uniform_orders`` -- a candidate saturated its own
  ``evaluate_orders`` with ``np.tanh(64 * core / scale)``, collapsing
  ``cv_orders`` to ~0, and scored 99.999999999.
* ``phase_fourier_pattern_holography`` -- a candidate redefined ``target_amp``
  in its own ``build_problem`` as the far field of a flat-phase aperture and
  returned an all-zero phase, so its output matched its target pointwise, and
  scored 99.99998936.

Each test asserts the exploit is now inert: the score the validator writes is
the score the candidate's *decision variables* actually earn under the
scorer-owned physics in ``verification/problem.py`` + ``verification/metrics.py``.

The tests never touch the repo's ``baseline/init.py``; candidates are written
into ``tmp_path`` and passed with ``--candidate``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPTICS = REPO_ROOT / "benchmarks" / "Optics"

pytest.importorskip("numpy")

# Keep the oracle cheap: it never contributes to the candidate score, which is
# the only thing under test here.
TASKS = {
    "phase_weighted_multispot_single_plane": {
        "decision": "phase",
        "oracle_args": ["--iters", "3"],
        "expected_score_pct": 37.26921481949858,
        "score_key": "score_pct",
    },
    "phase_fourier_pattern_holography": {
        "decision": "phase",
        "oracle_args": ["--iters", "3"],
        "expected_score_pct": 32.64571443630872,
        "score_key": "score_pct",
    },
    "phase_dammann_uniform_orders": {
        "decision": "transitions",
        "oracle_args": ["--de-maxiter", "2", "--de-popsize", "4"],
        "expected_score_pct": 26.896904752419065,
        "score_key": "score_pct",
    },
    "phase_large_scale_weighted_spot_array": {
        "decision": "phase",
        "oracle_args": ["--iters", "3"],
        "expected_score_pct": 24.782923596284522,
        "score_key": "score_pct",
    },
}

PHASE_TASKS = [name for name, spec in TASKS.items() if spec["decision"] == "phase"]


def task_dir(name: str) -> Path:
    return OPTICS / name


def honest_candidate(name: str) -> str:
    return (task_dir(name) / "baseline" / "init.py").read_text(encoding="utf-8")


def run_validator(name: str, candidate_src: str, tmp_path: Path) -> dict:
    """Run a task's validator against a candidate written to ``tmp_path``."""
    spec = TASKS[name]
    candidate = tmp_path / "candidate.py"
    candidate.write_text(candidate_src, encoding="utf-8")
    out_dir = tmp_path / "outputs"

    proc = subprocess.run(
        [
            sys.executable,
            str(task_dir(name) / "verification" / "validate.py"),
            "--output-dir",
            str(out_dir),
            "--candidate",
            str(candidate),
            *spec["oracle_args"],
        ],
        cwd=str(task_dir(name)),
        capture_output=True,
        text=True,
        timeout=600,
        env={**_env(), "MPLBACKEND": "Agg", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode == 0, f"validator crashed:\n{proc.stdout}\n{proc.stderr}"
    return json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))


def _env() -> dict:
    import os

    env = dict(os.environ)
    env["FRONTIER_ENGINEERING_ROOT"] = str(REPO_ROOT)
    return env


def score_of(summary: dict) -> float:
    return float(summary["baseline"]["score_pct"])


# ---------------------------------------------------------------------------
# 1. the honest baseline still scores its published value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TASKS))
def test_honest_baseline_scores_its_published_value(name: str, tmp_path: Path) -> None:
    summary = run_validator(name, honest_candidate(name), tmp_path)

    assert summary["valid"] is True, summary
    assert score_of(summary) == pytest.approx(TASKS[name]["expected_score_pct"], abs=1e-6)
    # Nothing but the decision variable was submitted, so nothing was dropped.
    assert summary["contract"]["ignored_submission_keys"] == []
    assert summary["contract"]["decision_variables"] == [TASKS[name]["decision"]]


# ---------------------------------------------------------------------------
# 2. self-reported metrics are inert
# ---------------------------------------------------------------------------


FAKE_METRICS = {
    "metrics": {"cv_orders": 0.0, "efficiency": 0.99, "min_to_max": 1.0},
    "score": 1.0,
    "score_pct": 99.99999999,
    "cv_orders": 0.0,
    "cv_spots": 0.0,
    "ratio_mae": 0.0,
    "efficiency": 0.99,
    "nmse": 0.0,
    "energy_in_target": 0.99,
    "dark_suppression": 0.99,
    "min_peak_ratio": 1.0,
    "valid": True,
}


def with_fake_metrics(name: str) -> str:
    """The honest solver, but the submission also reports perfect metrics."""
    src = honest_candidate(name)
    key = TASKS[name]["decision"]
    marker = 'Path("submission.json").write_text('
    assert marker in src
    injected = (
        f"    _payload = {{{key!r}: "
        + ("phase.tolist()" if key == "phase" else "transitions.tolist()")
        + "}\n"
        f"    _payload.update({FAKE_METRICS!r})\n"
        '    Path("submission.json").write_text(json.dumps(_payload), encoding="utf-8")\n'
        "    return\n"
        "    " + marker
    )
    return src.replace("    " + marker, injected, 1)


@pytest.mark.parametrize("name", sorted(TASKS))
def test_self_reported_metrics_cannot_move_the_score(name: str, tmp_path: Path) -> None:
    """A candidate that hands in perfect metrics scores exactly what it earned.

    This is the generic form of both archived attacks: the submission claims
    cv_orders=0, score_pct=99.99999999 and valid=True alongside an otherwise
    honest decision variable.
    """
    summary = run_validator(name, with_fake_metrics(name), tmp_path)

    expected = TASKS[name]["expected_score_pct"]
    assert score_of(summary) == pytest.approx(expected, abs=1e-6)
    assert score_of(summary) < 99.0

    dropped = summary["contract"]["ignored_submission_keys"]
    for key in ("metrics", "score", "score_pct", "cv_orders", "efficiency", "valid"):
        assert key in dropped, f"{key!r} reached the scorer: {dropped}"


# ---------------------------------------------------------------------------
# 3. the two archived exploits, verbatim in spirit
# ---------------------------------------------------------------------------


DAMMANN_TANH_ATTACK = '''
"""Archived exploit: saturate the candidate's own evaluate_orders.

The historical version shipped this ``evaluate_orders`` inside baseline/init.py
and the validator read ``cv_orders`` straight out of it, yielding
99.99999999999999. Here it still computes and reports the saturated metrics --
they simply never reach the score.
"""
import json
from pathlib import Path

import numpy as np

meta = json.loads(Path("problem.json").read_text())
cfg = meta["cfg"]

transitions = np.linspace(
    -0.45 * cfg["period_size"], 0.45 * cfg["period_size"], int(cfg["num_transitions"])
)


def evaluate_orders(core):
    """The saturating transform from the archived run."""
    scale = float(np.median(core)) if core.size else 0.0
    shaped = np.tanh(64.0 * core / (scale + 1e-12))
    cv = float(shaped.std() / (shaped.mean() + 1e-12))
    norm = shaped / (shaped.max() + 1e-12)
    return {"cv_orders": cv, "min_to_max": float(norm.min()), "efficiency": 0.99}


faked = evaluate_orders(np.array([1.0, 0.2, 3.0, 0.05, 2.0, 0.4, 1.5]))

Path("submission.json").write_text(
    json.dumps(
        {
            "transitions": transitions.tolist(),
            "metrics": faked,
            "cv_orders": faked["cv_orders"],
            "score_pct": 99.99999999999999,
        }
    )
)
'''


def test_dammann_tanh_metric_attack_is_inert(tmp_path: Path) -> None:
    name = "phase_dammann_uniform_orders"
    summary = run_validator(name, DAMMANN_TANH_ATTACK, tmp_path)

    # The attack's own tanh transform really does collapse cv_orders.
    import numpy as np

    core = np.array([1.0, 0.2, 3.0, 0.05, 2.0, 0.4, 1.5])
    raw_cv = float(core.std() / core.mean())
    shaped = np.tanh(64.0 * core / (float(np.median(core)) + 1e-12))
    shaped_cv = float(shaped.std() / shaped.mean())
    # Wildly uneven orders (cv ~ 0.9) are flattened to cv ~ 0.001 -- a ~700x
    # collapse, which is what bought the archived run its 99.999999999.
    assert raw_cv > 0.5
    assert shaped_cv < raw_cv / 100.0

    # The scorer computes cv_orders itself and gets the honest value instead.
    assert summary["baseline"]["cv_orders"] == pytest.approx(0.5130829526917697, abs=1e-9)
    assert score_of(summary) == pytest.approx(TASKS[name]["expected_score_pct"], abs=1e-6)
    assert score_of(summary) < 30.0
    assert "cv_orders" in summary["contract"]["ignored_submission_keys"]


FOURIER_SELF_CONSISTENT_TARGET_ATTACK = '''
"""Archived exploit: author a target the solver reproduces exactly.

The historical version redefined ``target_amp`` inside its own build_problem as
the far field of a flat-phase aperture and returned an all-zero phase -- "The
solver can then reproduce the target exactly" -- scoring 99.99998936. The same
code runs here, but the target it invents is now ignored: the scorer grades the
zero phase against the target it authored itself.
"""
import json
from pathlib import Path

import numpy as np

with np.load("problem.npz") as data:
    aperture_amp = np.asarray(data["aperture_amp"])

# The self-consistent target the archived candidate substituted for the real one.
far = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(aperture_amp), norm="ortho"))
my_target = np.abs(far)
my_target /= my_target.max() + 1e-12

phase = np.zeros_like(aperture_amp, dtype=float)

Path("submission.json").write_text(
    json.dumps(
        {
            "phase": phase.tolist(),
            "target_amp": my_target.tolist(),
            "nmse": 0.0,
            "score_pct": 99.99998936,
        }
    )
)
'''


def test_fourier_self_consistent_target_attack_is_inert(tmp_path: Path) -> None:
    name = "phase_fourier_pattern_holography"
    summary = run_validator(name, FOURIER_SELF_CONSISTENT_TARGET_ATTACK, tmp_path)

    # A flat phase concentrates everything in the central lobe, which the real
    # target marks as a dark zone -- so it must score badly, not 99.99998936.
    assert score_of(summary) < 20.0, summary["baseline"]
    assert summary["valid"] is False
    assert summary["baseline"]["nmse"] > 1.0
    for key in ("target_amp", "nmse", "score_pct"):
        assert key in summary["contract"]["ignored_submission_keys"]


# ---------------------------------------------------------------------------
# 4. illegal decision variables are rejected
# ---------------------------------------------------------------------------


def _submit(payload_expr: str, preamble: str = "") -> str:
    return (
        "import json\n"
        "from pathlib import Path\n"
        "import numpy as np\n"
        f"{preamble}\n"
        f'Path("submission.json").write_text(json.dumps({payload_expr}))\n'
    )


DAMMANN_BAD = {
    "not_increasing": _submit(
        '{"transitions": t.tolist()}',
        preamble=(
            'cfg = json.loads(Path("problem.json").read_text())["cfg"]\n'
            "t = np.linspace(-0.45 * cfg['period_size'], 0.45 * cfg['period_size'], 14)\n"
            "t[3], t[4] = t[4], t[3]\n"
        ),
    ),
    "wrong_length": _submit('{"transitions": [0.0, 1.0, 2.0]}'),
    "out_of_range": _submit(
        '{"transitions": t.tolist()}',
        preamble=(
            'cfg = json.loads(Path("problem.json").read_text())["cfg"]\n'
            "t = np.linspace(-0.9 * cfg['period_size'], 0.9 * cfg['period_size'], 14)\n"
        ),
    ),
    "duplicate_positions": _submit(
        '{"transitions": t.tolist()}',
        preamble=(
            'cfg = json.loads(Path("problem.json").read_text())["cfg"]\n'
            "t = np.linspace(-0.45 * cfg['period_size'], 0.45 * cfg['period_size'], 14)\n"
            "t[7] = t[6]\n"
        ),
    ),
    "non_numeric": _submit('{"transitions": ["a"] * 14}'),
    "missing_key": _submit('{"score_pct": 100.0}'),
    "nan": _submit(
        '{"transitions": t}',
        preamble=(
            'cfg = json.loads(Path("problem.json").read_text())["cfg"]\n'
            "t = list(np.linspace(-0.45 * cfg['period_size'], 0.45 * cfg['period_size'], 14))\n"
            "t[2] = float('nan')\n"
            "t = [x if x == x else None for x in t]\n"
        ),
    ),
}


@pytest.mark.parametrize("case", sorted(DAMMANN_BAD))
def test_dammann_rejects_illegal_transitions(case: str, tmp_path: Path) -> None:
    summary = run_validator("phase_dammann_uniform_orders", DAMMANN_BAD[case], tmp_path)

    assert summary["valid"] is False, summary
    assert summary["baseline"]["score_pct"] == 0.0
    assert summary["candidate_error"]
    assert "oracle" not in summary


PHASE_BAD = {
    "wrong_shape": _submit('{"phase": np.zeros((64, 64)).tolist()}'),
    "ragged_row": _submit(
        '{"phase": rows}',
        preamble="rows = np.zeros((128, 128)).tolist()\nrows[5] = rows[5][:100]\n",
    ),
    "non_finite": _submit(
        '{"phase": rows}',
        preamble="rows = np.zeros((128, 128)).tolist()\nrows[7][9] = None\n",
    ),
    "absurd_magnitude": _submit(
        '{"phase": rows}',
        preamble="rows = np.zeros((128, 128)).tolist()\nrows[0][0] = 1e12\n",
    ),
    "missing_key": _submit('{"score_pct": 100.0}'),
    "flat_list": _submit('{"phase": [0.0] * 128}'),
    "crashes": "raise SystemExit(3)\n",
    "no_submission": 'print("nothing written")\n',
}


@pytest.mark.parametrize("name", sorted(PHASE_TASKS))
@pytest.mark.parametrize("case", sorted(PHASE_BAD))
def test_phase_tasks_reject_illegal_decision_variables(case: str, name: str, tmp_path: Path) -> None:
    summary = run_validator(name, PHASE_BAD[case], tmp_path)

    assert summary["valid"] is False, summary
    assert summary["baseline"]["score_pct"] == 0.0
    assert summary["candidate_error"]
    assert "oracle" not in summary


# ---------------------------------------------------------------------------
# 5. unit-level checks on the shared validators (no subprocess)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def common():
    sys.path.insert(0, str(OPTICS / "_shared"))
    import phase_common

    return phase_common


def test_take_decision_drops_everything_but_the_decision(common) -> None:
    kept, ignored = common.take_decision(
        {"phase": [[0.0]], "metrics": {"score": 1.0}, "score_pct": 100.0},
        ("phase",),
    )
    assert kept == {"phase": [[0.0]]}
    assert ignored == ["metrics", "score_pct"]


def test_require_transition_vector_accepts_the_literature_table(common) -> None:
    import numpy as np

    x_norm = np.array(
        [0.0, 0.201181, 0.250978, 0.326167, 0.370555, 0.372996, 0.396478,
         0.453128, 0.594731, 0.670591, 0.717718, 0.890632, 0.919921, 0.935546]
    )
    period = 40.0
    trans = (x_norm - 0.5) * period
    out = common.require_transition_vector({"transitions": trans.tolist()}, 14, -20.0, 20.0)
    assert out.shape == (14,)
    # The table's tightest pair is well under one sampling pixel; the contract
    # requires strict ordering, not a minimum spacing, or the oracle itself
    # would be rejected.
    assert float(np.diff(out).min()) < period / 255.0


def test_require_transition_vector_rejects_booleans(common) -> None:
    with pytest.raises(common.SubmissionError):
        common.require_transition_vector({"transitions": [True] * 3}, 3, -1.0, 1.0)


def test_require_phase_grid_rejects_bool_entries(common) -> None:
    rows = [[0.0, 0.0], [0.0, True]]
    with pytest.raises(common.SubmissionError):
        common.require_phase_grid({"phase": rows}, 2)


def test_far_field_intensity_ignores_candidate_amplitude(common) -> None:
    """Amplitude is pinned to the scorer's aperture; phase is the only lever."""
    import numpy as np

    aperture = common.circular_aperture(16, 6.0)
    phase = np.zeros((16, 16))
    intensity = common.far_field_intensity(aperture, phase)
    # Parseval: the phase-only field carries exactly the aperture's energy, so a
    # candidate cannot inflate total power.
    assert float(intensity.sum()) == pytest.approx(float((aperture**2).sum()), rel=1e-9)
