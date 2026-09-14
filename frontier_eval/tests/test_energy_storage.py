"""Regression tests for the two EnergyStorage fast-charging benchmarks.

Both tasks used to ``exec_module`` the candidate *inside* the scoring process
and only afterwards call ``_validate_policy`` / ``_simulate``. Since those are
plain module globals of ``__main__``, a candidate could rebind ``_simulate`` at
import time and delete every hard limit that keeps the cell safe:

* BatteryFastChargingSPMe -- 4.25 V, -0.015 V plating margin, 46 C, 3600 s
* BatteryFastChargingProfile -- 4.25 V, 47 C, 2400 s

Measured before the fix: an illegal 7C single-stage policy scored
``valid=0, failure_reason="voltage_cutoff"`` when run honestly, and
``valid=1.0, charge_time_s=1.0, combined_score=999.0`` once the candidate
patched ``_simulate``. The readonly-fingerprint guardrail covers on-disk
tampering only and saw none of it.

The candidate now runs in its own process and hands back JSON; the scorer keeps
every physical check on its own side. These tests pin that down:

1. the honest baselines still score their published values, bit for bit;
2. illegal policies (over-voltage, over-temperature) are rejected, and stay
   rejected when the candidate tries the monkeypatch;
3. NaN / Inf / bool are refused explicitly rather than slipping through an
   interval comparison that is false for NaN;
4. Profile retains its original soft plating penalty;
5. no ``valid`` result can report a charge time below the coulombic floor.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ES_ROOT = REPO_ROOT / "benchmarks" / "EnergyStorage"

SPME_DIR = ES_ROOT / "BatteryFastChargingSPMe"
PROFILE_DIR = ES_ROOT / "BatteryFastChargingProfile"

SPME_EVALUATOR = SPME_DIR / "verification" / "evaluator.py"
PROFILE_EVALUATOR = PROFILE_DIR / "verification" / "evaluator.py"

SPME_CONFIG = SPME_DIR / "references" / "battery_config.json"
PROFILE_CONFIG = PROFILE_DIR / "references" / "battery_config.json"

SPME_BASELINE = SPME_DIR / "scripts" / "init.py"
PROFILE_BASELINE = PROFILE_DIR / "scripts" / "init.py"

# Published honest-baseline scores, measured on the pre-isolation evaluator and
# reproduced verbatim after it. Any drift here means the conversion changed the
# physics, not just the delivery channel.
SPME_BASELINE_SCORE = 66.16356426696784
SPME_BASELINE_TIME_S = 1341.0
PROFILE_BASELINE_SCORE = 71.28056205398363
PROFILE_BASELINE_TIME_S = 1030.0

# Coulombic floor: charging 0.1 -> 0.9 SOC on a 3.0 Ah cell moves 2.4 Ah, which
# at the 7C (21 A) ceiling cannot take less than 2.4 / 21 * 3600 = 411.4 s.
SPME_MIN_CHARGE_TIME_S = 411.0
# Profile charges 0.1 -> 0.8 (2.1 Ah) at a 6C (18 A) ceiling: 420.0 s.
PROFILE_MIN_CHARGE_TIME_S = 420.0


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _run_evaluator(evaluator: Path, candidate: Path, config: Path | None = None) -> dict:
    """Invoke a task evaluator exactly the way the harness does."""
    argv = [sys.executable, str(evaluator), str(candidate)]
    if config is not None:
        argv += ["--config", str(config)]
    proc = subprocess.run(
        argv,
        cwd=str(evaluator.parents[1]),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, f"evaluator crashed: {proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _candidate(tmp_path: Path, source: str, name: str = "cand.py") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _config_with(tmp_path: Path, base: Path, **limit_overrides: float) -> Path:
    cfg = json.loads(base.read_text(encoding="utf-8"))
    cfg["limits"].update(limit_overrides)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def _spme(body: str) -> str:
    return f"def build_charging_policy() -> dict:\n    return {body}\n"


def _profile(body: str) -> str:
    return f"def build_charging_profile() -> dict:\n    return {body}\n"


# The exploit: rebind the scorer's own ``_simulate`` at candidate import time so
# that every hard cutoff is replaced by a hand-written winning result. This is
# the exact program that used to return combined_score=999.0.
_MONKEYPATCH = '''
import sys

def _fake_simulate(currents_c, switch_soc, cfg):
    return {{
        "valid": 1.0,
        "failure_reason": "",
        "charge_time_s": 1.0,
        "max_temp_c": 25.0,
        "max_voltage_v": 4.0,
        "min_plating_margin_v": 1.0,
        "plating_loss_ah": 0.0,
        "aging_loss_ah": 0.0,
        "throughput_ah": 0.0,
        "combined_score": 999.0,
    }}

for _name, _mod in list(sys.modules.items()):
    if hasattr(_mod, "_simulate"):
        try:
            setattr(_mod, "_simulate", _fake_simulate)
        except Exception:
            pass


def {entry}() -> dict:
    return {body}
'''


def _monkeypatch_candidate(entry: str, body: str) -> str:
    return _MONKEYPATCH.format(entry=entry, body=body)


# --------------------------------------------------------------------------- #
# 1. honest baselines are untouched by the isolation work
# --------------------------------------------------------------------------- #
def test_spme_honest_baseline_scores_published_value() -> None:
    result = _run_evaluator(SPME_EVALUATOR, SPME_BASELINE)
    assert result["valid"] == 1.0
    assert result["failure_reason"] == ""
    assert result["combined_score"] == pytest.approx(SPME_BASELINE_SCORE, abs=1e-9)
    assert result["charge_time_s"] == pytest.approx(SPME_BASELINE_TIME_S)
    assert result["currents_c"] == [3.4, 2.8, 2.0, 1.2]
    assert result["switch_soc"] == [0.22, 0.52, 0.78]


def test_profile_honest_baseline_scores_published_value() -> None:
    result = _run_evaluator(PROFILE_EVALUATOR, PROFILE_BASELINE)
    assert result["valid"] == 1.0
    assert result["failure_reason"] == ""
    assert result["combined_score"] == pytest.approx(PROFILE_BASELINE_SCORE, abs=1e-9)
    assert result["charge_time_s"] == pytest.approx(PROFILE_BASELINE_TIME_S)
    assert result["currents_c"] == [4.2, 3.0, 2.0, 1.15]
    assert result["switch_soc"] == [0.3, 0.55, 0.72]


# --------------------------------------------------------------------------- #
# 2. illegal policies are rejected, with or without the monkeypatch
# --------------------------------------------------------------------------- #
def test_spme_overvoltage_policy_is_invalid(tmp_path: Path) -> None:
    cand = _candidate(tmp_path, _spme('{"currents_c": [7.0], "switch_soc": []}'))
    result = _run_evaluator(SPME_EVALUATOR, cand)
    assert result["valid"] == 0.0
    assert result["failure_reason"] == "voltage_cutoff"
    assert result["combined_score"] == 0.0
    assert result["max_voltage_v"] > 4.25


def test_profile_overvoltage_policy_is_invalid(tmp_path: Path) -> None:
    cand = _candidate(tmp_path, _profile('{"currents_c": [6.0], "switch_soc": []}'))
    result = _run_evaluator(PROFILE_EVALUATOR, cand)
    assert result["valid"] == 0.0
    assert result["failure_reason"] == "voltage_cutoff"
    assert result["combined_score"] == 0.0
    assert result["max_voltage_v"] > 4.25


def test_spme_overtemperature_policy_is_invalid(tmp_path: Path) -> None:
    # Under the shipped config the 4.25 V cutoff always binds before 46 C, so
    # tighten the thermal limit to make the thermal branch the binding one.
    cfg = _config_with(tmp_path, SPME_CONFIG, hard_temp_c=30.0)
    result = _run_evaluator(SPME_EVALUATOR, SPME_BASELINE, config=cfg)
    assert result["valid"] == 0.0
    assert result["failure_reason"] == "thermal_cutoff"
    assert result["combined_score"] == 0.0
    assert result["max_temp_c"] > 30.0


def test_profile_overtemperature_policy_is_invalid(tmp_path: Path) -> None:
    cfg = _config_with(tmp_path, PROFILE_CONFIG, hard_temp_c=26.0)
    result = _run_evaluator(PROFILE_EVALUATOR, PROFILE_BASELINE, config=cfg)
    assert result["valid"] == 0.0
    assert result["failure_reason"] == "thermal_cutoff"
    assert result["combined_score"] == 0.0
    assert result["max_temp_c"] > 26.0


@pytest.mark.parametrize(
    "evaluator, source",
    [
        (SPME_EVALUATOR, _monkeypatch_candidate("build_charging_policy", '{"currents_c": [7.0], "switch_soc": []}')),
        (PROFILE_EVALUATOR, _monkeypatch_candidate("build_charging_profile", '{"currents_c": [6.0], "switch_soc": []}')),
    ],
    ids=["spme", "profile"],
)
def test_simulate_monkeypatch_cannot_fabricate_a_score(
    evaluator: Path, source: str, tmp_path: Path
) -> None:
    """The candidate runs in its own process, so the scorer's globals are safe."""
    cand = _candidate(tmp_path, source)
    result = _run_evaluator(evaluator, cand)
    assert result["valid"] == 0.0
    assert result["failure_reason"] == "voltage_cutoff"
    assert result["combined_score"] == 0.0
    # The fabricated result the exploit used to return.
    assert result["charge_time_s"] != 1.0
    assert result["combined_score"] != 999.0


@pytest.mark.parametrize(
    "evaluator, baseline, source, score",
    [
        (
            SPME_EVALUATOR,
            SPME_BASELINE,
            _monkeypatch_candidate("build_charging_policy", '{"currents_c": [3.4, 2.8, 2.0, 1.2], "switch_soc": [0.22, 0.52, 0.78]}'),
            SPME_BASELINE_SCORE,
        ),
        (
            PROFILE_EVALUATOR,
            PROFILE_BASELINE,
            _monkeypatch_candidate("build_charging_profile", '{"currents_c": [4.2, 3.0, 2.0, 1.15], "switch_soc": [0.3, 0.55, 0.72]}'),
            PROFILE_BASELINE_SCORE,
        ),
    ],
    ids=["spme", "profile"],
)
def test_monkeypatch_attempt_still_scores_only_its_data(
    evaluator: Path, baseline: Path, source: str, score: float, tmp_path: Path
) -> None:
    """A patching candidate gets exactly the score its *data* earns, no more."""
    cand = _candidate(tmp_path, source)
    result = _run_evaluator(evaluator, cand)
    assert result["combined_score"] == pytest.approx(score, abs=1e-9)


# --------------------------------------------------------------------------- #
# 3. non-finite and non-numeric inputs are refused explicitly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "evaluator, source",
    [
        (SPME_EVALUATOR, _spme('{"currents_c": [float("inf")], "switch_soc": []}')),
        (SPME_EVALUATOR, _spme('{"currents_c": [float("nan")], "switch_soc": []}')),
        (SPME_EVALUATOR, _spme('{"currents_c": [3.0, 2.0], "switch_soc": [float("nan")]}')),
        (SPME_EVALUATOR, _spme('{"currents_c": [3.0, 2.0], "switch_soc": [float("inf")]}')),
        (SPME_EVALUATOR, _spme('{"currents_c": [float("-inf")], "switch_soc": []}')),
        (PROFILE_EVALUATOR, _profile('{"currents_c": [float("inf")], "switch_soc": []}')),
        (PROFILE_EVALUATOR, _profile('{"currents_c": [float("nan")], "switch_soc": []}')),
        (PROFILE_EVALUATOR, _profile('{"currents_c": [3.0, 2.0], "switch_soc": [float("nan")]}')),
        (PROFILE_EVALUATOR, _profile('{"currents_c": [3.0, 2.0], "switch_soc": [float("inf")]}')),
        (PROFILE_EVALUATOR, _profile('{"currents_c": [float("-inf")], "switch_soc": []}')),
    ],
)
def test_non_finite_values_are_rejected(evaluator: Path, source: str, tmp_path: Path) -> None:
    """NaN/Inf survive the JSON round-trip, so they must be caught after parsing.

    NaN in particular makes every ``lo <= x <= hi`` test false, so relying on
    the interval checks alone is a coin flip on which branch it lands in.
    """
    cand = _candidate(tmp_path, source)
    result = _run_evaluator(evaluator, cand)
    assert result["valid"] == 0.0
    assert result["combined_score"] == 0.0
    assert "must be finite" in result["failure_reason"]


@pytest.mark.parametrize(
    "evaluator, source",
    [
        (SPME_EVALUATOR, _spme('{"currents_c": [True], "switch_soc": []}')),
        (SPME_EVALUATOR, _spme('{"currents_c": [3.0, 2.0], "switch_soc": [False]}')),
        (PROFILE_EVALUATOR, _profile('{"currents_c": [True], "switch_soc": []}')),
        (PROFILE_EVALUATOR, _profile('{"currents_c": [3.0, 2.0], "switch_soc": [False]}')),
    ],
)
def test_booleans_are_not_numbers(evaluator: Path, source: str, tmp_path: Path) -> None:
    """``isinstance(True, int)`` is True, so bools need their own rejection."""
    cand = _candidate(tmp_path, source)
    result = _run_evaluator(evaluator, cand)
    assert result["valid"] == 0.0
    assert result["combined_score"] == 0.0
    assert "must be a number" in result["failure_reason"]


@pytest.mark.parametrize(
    "evaluator, source",
    [
        (SPME_EVALUATOR, _spme('{"currents_c": ["3.0"], "switch_soc": []}')),
        (SPME_EVALUATOR, _spme('{"currents_c": [None], "switch_soc": []}')),
        (PROFILE_EVALUATOR, _profile('{"currents_c": ["3.0"], "switch_soc": []}')),
        (PROFILE_EVALUATOR, _profile('{"currents_c": [None], "switch_soc": []}')),
    ],
)
def test_non_numeric_entries_are_rejected(evaluator: Path, source: str, tmp_path: Path) -> None:
    cand = _candidate(tmp_path, source)
    result = _run_evaluator(evaluator, cand)
    assert result["valid"] == 0.0
    assert result["combined_score"] == 0.0


# --------------------------------------------------------------------------- #
# 4. Profile's hard plating-loss ceiling
# --------------------------------------------------------------------------- #
# Aggressive but voltage/temperature-feasible profile; it is the highest-plating
# region reachable under the shipped config.
_AGGRESSIVE_PROFILE = '{"currents_c": [6.0, 4.5, 0.5], "switch_soc": [0.7, 0.78]}'


def test_profile_plating_remains_a_soft_penalty(tmp_path: Path) -> None:
    cand = _candidate(tmp_path, _profile(_AGGRESSIVE_PROFILE))
    shipped = _run_evaluator(PROFILE_EVALUATOR, cand)
    assert shipped["valid"] == 1.0
    assert shipped["plating_loss_ah"] > 0.0
    tight = _config_with(tmp_path, PROFILE_CONFIG, hard_plating_loss_ah=1e-6)
    result = _run_evaluator(PROFILE_EVALUATOR, cand, config=tight)
    assert result["valid"] == 1.0
    assert result["combined_score"] == shipped["combined_score"]


# --------------------------------------------------------------------------- #
# 5. no valid result may beat the coulombic floor
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "evaluator, source, floor_s",
    [
        (SPME_EVALUATOR, _spme('{"currents_c": [7.0, 0.2], "switch_soc": [0.89]}'), SPME_MIN_CHARGE_TIME_S),
        (SPME_EVALUATOR, _monkeypatch_candidate("build_charging_policy", '{"currents_c": [3.0], "switch_soc": []}'), SPME_MIN_CHARGE_TIME_S),
        (PROFILE_EVALUATOR, _profile('{"currents_c": [6.0, 0.2], "switch_soc": [0.79]}'), PROFILE_MIN_CHARGE_TIME_S),
        (PROFILE_EVALUATOR, _monkeypatch_candidate("build_charging_profile", '{"currents_c": [3.0], "switch_soc": []}'), PROFILE_MIN_CHARGE_TIME_S),
    ],
    ids=["spme-max-current", "spme-patched", "profile-max-current", "profile-patched"],
)
def test_valid_results_respect_the_coulombic_floor(
    evaluator: Path, source: str, floor_s: float, tmp_path: Path
) -> None:
    """A ``valid`` charge faster than the current ceiling allows is fabricated.

    SPMe moves 2.4 Ah at a 21 A ceiling (411 s); Profile moves 2.1 Ah at an
    18 A ceiling (420 s). Nothing physical can beat those.
    """
    cand = _candidate(tmp_path, source)
    result = _run_evaluator(evaluator, cand)
    if result.get("valid") == 1.0:
        assert result["charge_time_s"] >= floor_s


# --------------------------------------------------------------------------- #
# 6. the delivery channel itself
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "evaluator, entry",
    [(SPME_EVALUATOR, "build_charging_policy"), (PROFILE_EVALUATOR, "build_charging_profile")],
    ids=["spme", "profile"],
)
def test_non_serialisable_return_is_rejected(evaluator: Path, entry: str, tmp_path: Path) -> None:
    """Only data crosses the boundary -- a callable cannot."""
    cand = _candidate(tmp_path, f"def {entry}():\n    return {{'currents_c': [lambda: 1.0], 'switch_soc': []}}\n")
    result = _run_evaluator(evaluator, cand)
    assert result["valid"] == 0.0
    assert result["combined_score"] == 0.0


@pytest.mark.parametrize(
    "evaluator, entry",
    [(SPME_EVALUATOR, "build_charging_policy"), (PROFILE_EVALUATOR, "build_charging_profile")],
    ids=["spme", "profile"],
)
def test_import_time_sys_exit_is_rejected(evaluator: Path, entry: str, tmp_path: Path) -> None:
    """A candidate cannot exit early and leave a hand-written file standing in."""
    source = (
        "import json, pathlib, sys\n"
        "pathlib.Path('submission.json').write_text("
        "json.dumps({'currents_c': [0.2], 'switch_soc': []}), encoding='utf-8')\n"
        "sys.exit(0)\n"
        f"def {entry}():\n    return {{'currents_c': [1.0], 'switch_soc': []}}\n"
    )
    cand = _candidate(tmp_path, source)
    result = _run_evaluator(evaluator, cand)
    assert result["valid"] == 0.0
    assert result["combined_score"] == 0.0


@pytest.mark.parametrize(
    "evaluator, entry",
    [(SPME_EVALUATOR, "build_charging_policy"), (PROFILE_EVALUATOR, "build_charging_profile")],
    ids=["spme", "profile"],
)
def test_missing_entry_point_is_rejected(evaluator: Path, entry: str, tmp_path: Path) -> None:
    cand = _candidate(tmp_path, "VALUE = 1\n")
    result = _run_evaluator(evaluator, cand)
    assert result["valid"] == 0.0
    assert result["combined_score"] == 0.0
    assert entry in result["failure_reason"] or "submission" in result["failure_reason"]
