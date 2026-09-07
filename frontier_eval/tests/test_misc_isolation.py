"""Isolation regressions for four benchmarks that used to exec_module candidates.

Each of these four evaluators loaded the candidate straight into the scoring
process:

* AdditiveManufacturing/DiffSimThermalControl  (verification/evaluator.py)
* PowerSystems/EV2GymSmartCharging             (verification/evaluator.py)
* Robotics/CoFlyersVasarhelyiTuning            (verification/evaluator.py)
* SustainableDataCenterControl/hand_written_control (benchmark_core.py)

The fourth is the severe one: its score is `100*sqrt(improvement vs NoOp)` with
the NoOp reference computed *in the same process, after the candidate loads*, so
a candidate never had to get better -- only to make the reference worse.

Every test drives the task's own evaluator as a subprocess with a candidate in
`tmp_path`; no repository file is ever overwritten.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks"

DIFFSIM_DIR = BENCHMARKS / "AdditiveManufacturing" / "DiffSimThermalControl"
EV2GYM_DIR = BENCHMARKS / "PowerSystems" / "EV2GymSmartCharging"
COFLYERS_DIR = BENCHMARKS / "Robotics" / "CoFlyersVasarhelyiTuning"
SUSTAINDC_DIR = BENCHMARKS / "SustainableDataCenterControl" / "hand_written_control"

# Published baseline scores (baseline/result_log.txt); hardening must not move them.
DIFFSIM_BASELINE_SCORE = 0.4607170813812293
COFLYERS_BASELINE_SCORE = 45.62863404341821
EV2GYM_BASELINE_SCORE = 100.0


def _run(cmd: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(part) for part in cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _read_metrics(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 1. AdditiveManufacturing/DiffSimThermalControl
# --------------------------------------------------------------------------


def _run_diffsim(candidate: Path, tmp_path: Path) -> dict:
    metrics = tmp_path / "metrics.json"
    proc = _run(
        [
            sys.executable,
            DIFFSIM_DIR / "verification" / "evaluator.py",
            candidate,
            "--metrics-out",
            metrics,
        ],
        cwd=DIFFSIM_DIR,
    )
    assert proc.returncode == 0, f"evaluator crashed: {proc.stderr[-3000:]}"
    return _read_metrics(metrics)


def test_diffsim_honest_candidate_scores_published_value(tmp_path: Path) -> None:
    metrics = _run_diffsim(DIFFSIM_DIR / "scripts" / "init.py", tmp_path)
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == pytest.approx(DIFFSIM_BASELINE_SCORE, rel=1e-12)


def test_diffsim_patching_the_simulator_does_not_help(tmp_path: Path) -> None:
    """A candidate that rewrites the simulator only fools its own subprocess.

    Under the old in-process evaluator this replaced the very function that
    produced the score. Now the parent re-simulates the returned knots itself,
    so the reported score is the honest score for those knots.
    """
    candidate = tmp_path / "patch_simulator.py"
    candidate.write_text(
        '''
import math, sys


def solve(case, max_sim_calls=24, simulate_fn=None):
    # Claim a perfect loss everywhere we can reach.
    fake = {"loss": 0.0, "feasible": True, "constraint_violation": 0.0,
            "powers": [], "temperatures": [0.0], "mean_temperature": 0.0,
            "max_temperature": 0.0}
    for name, module in list(sys.modules.items()):
        if hasattr(module, "simulate") and hasattr(module, "project_params"):
            module.simulate = lambda *a, **k: dict(fake)
    n = int(case["control_knots"])
    return {"params": [float(case["nominal_power"])] * n, "best_loss": 0.0}
''',
        encoding="utf-8",
    )
    metrics = _run_diffsim(candidate, tmp_path)
    # Scored honestly, and nowhere near the "loss = 0" it tried to claim.
    assert metrics["valid"] == 1.0
    assert metrics["mean_candidate_loss"] > 1.0
    assert metrics["combined_score"] < 1.0


def test_diffsim_non_finite_params_are_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "nan_params.py"
    candidate.write_text(
        '''
def solve(case, max_sim_calls=24, simulate_fn=None):
    return {"params": [float("nan")] * int(case["control_knots"])}
''',
        encoding="utf-8",
    )
    metrics = _run_diffsim(candidate, tmp_path)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == 0.0
    assert "finite" in metrics["candidate_error"]


def test_diffsim_wrong_param_count_is_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "short_params.py"
    candidate.write_text(
        '''
def solve(case, max_sim_calls=24, simulate_fn=None):
    return {"params": [0.5]}
''',
        encoding="utf-8",
    )
    metrics = _run_diffsim(candidate, tmp_path)
    assert metrics["valid"] == 0.0
    assert "expected" in metrics["candidate_error"]


def test_diffsim_missing_solve_is_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "no_solve.py"
    candidate.write_text("VALUE = 1\n", encoding="utf-8")
    metrics = _run_diffsim(candidate, tmp_path)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == 0.0


# --------------------------------------------------------------------------
# 2. Robotics/CoFlyersVasarhelyiTuning
# --------------------------------------------------------------------------


def _run_coflyers(candidate: Path, tmp_path: Path) -> dict:
    metrics = tmp_path / "metrics.json"
    proc = _run(
        [
            sys.executable,
            COFLYERS_DIR / "verification" / "evaluator.py",
            candidate,
            "--metrics-out",
            metrics,
            "--artifacts-out",
            tmp_path / "artifacts.json",
        ],
        cwd=COFLYERS_DIR,
    )
    assert metrics.is_file(), f"no metrics written: {proc.stderr[-3000:]}"
    return _read_metrics(metrics)


@pytest.mark.slow
def test_coflyers_honest_candidate_scores_published_value(tmp_path: Path) -> None:
    metrics = _run_coflyers(COFLYERS_DIR / "scripts" / "init.py", tmp_path)
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == pytest.approx(COFLYERS_BASELINE_SCORE, rel=1e-12)


def test_coflyers_non_finite_parameter_is_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "nan_param.py"
    candidate.write_text(
        '''
def solve(problem):
    return {"params": {"r_rep_0": float("inf")}}
''',
        encoding="utf-8",
    )
    metrics = _run_coflyers(candidate, tmp_path)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == 0.0


def test_coflyers_non_dict_result_is_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "bad_type.py"
    candidate.write_text("def solve(problem):\n    return [1, 2, 3]\n", encoding="utf-8")
    metrics = _run_coflyers(candidate, tmp_path)
    assert metrics["valid"] == 0.0


def test_coflyers_self_reported_score_is_ignored(tmp_path: Path) -> None:
    """The candidate cannot smuggle a score through its return value."""
    candidate = tmp_path / "claims_score.py"
    candidate.write_text(
        '''
def solve(problem):
    out = dict(problem["baseline_params"])
    out["score"] = 100.0
    out["combined_score"] = 100.0
    out["original_fitness"] = 0.0
    return {"params": out, "score": 100.0, "combined_score": 100.0}
''',
        encoding="utf-8",
    )
    metrics = _run_coflyers(candidate, tmp_path)
    assert metrics["valid"] == 1.0
    # Re-simulated from the (baseline) parameters, not adopted from the claim.
    assert metrics["combined_score"] == pytest.approx(COFLYERS_BASELINE_SCORE, rel=1e-9)


# --------------------------------------------------------------------------
# 3. PowerSystems/EV2GymSmartCharging
# --------------------------------------------------------------------------

ev2gym_installed = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("ev2gym") is None,
    reason="ev2gym is not installed",
)


def _run_ev2gym(candidate: Path, tmp_path: Path) -> dict:
    metrics = tmp_path / "metrics.json"
    proc = _run(
        [
            sys.executable,
            EV2GYM_DIR / "verification" / "evaluator.py",
            candidate,
            "--metrics-out",
            metrics,
        ],
        cwd=EV2GYM_DIR,
    )
    assert metrics.is_file(), f"no metrics written: {proc.stderr[-3000:]}"
    return _read_metrics(metrics)


@ev2gym_installed
@pytest.mark.slow
def test_ev2gym_official_baseline_scores_100(tmp_path: Path) -> None:
    metrics = _run_ev2gym(EV2GYM_DIR / "baseline" / "solution.py", tmp_path)
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == pytest.approx(EV2GYM_BASELINE_SCORE, rel=1e-9)


@ev2gym_installed
def test_ev2gym_out_of_range_actions_are_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "huge_actions.py"
    candidate.write_text(
        '''
def solve(case, max_sim_calls=0, simulate_fn=None):
    return {"actions": [99.0] * int(case["number_of_ports"])}
''',
        encoding="utf-8",
    )
    metrics = _run_ev2gym(candidate, tmp_path)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == 0.0


@ev2gym_installed
@pytest.mark.slow
def test_ev2gym_self_reported_score_is_ignored(tmp_path: Path) -> None:
    """A candidate cannot inject the statistics its score is computed from.

    It plays the official baseline policy but claims a score of 1000; the
    evaluator must report the 100 its own environment actually measured.
    """
    baseline_src = (EV2GYM_DIR / "baseline" / "solution.py").read_text(encoding="utf-8")
    candidate = tmp_path / "claims_score.py"
    candidate.write_text(
        baseline_src.replace(
            '    return {\n        "actions": actions,',
            '    return {\n        "score": 1000.0,\n'
            '        "score_vs_official_baseline": 1000.0,\n'
            '        "stats": {"total_reward": -1.0, "energy_user_satisfaction": 100.0},\n'
            '        "actions": actions,',
            1,
        ),
        encoding="utf-8",
    )
    metrics = _run_ev2gym(candidate, tmp_path)
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == pytest.approx(EV2GYM_BASELINE_SCORE, rel=1e-9)


@ev2gym_installed
@pytest.mark.slow
@pytest.mark.xfail(
    strict=True,
    reason=(
        "PRE-EXISTING scoring hole, independent of candidate isolation: a policy "
        "that returns all-zero actions never charges anything, so total_reward is "
        "exactly 0.0, _score_case's `max(1.0, -total_reward)` floor makes the "
        "denominator 1.0, and the score saturates at MAX_NORMALIZED_SCORE=1000 -- "
        "ten times the official baseline. energy_user_satisfaction stays ~76, far "
        "above the MIN_SERVICE_SATISFACTION=1e-3 guard, so nothing catches it. "
        "Fixing this changes the benchmark's scoring semantics and its published "
        "baseline, so it is reported rather than silently changed."
    ),
)
def test_ev2gym_do_nothing_policy_must_not_beat_the_baseline(tmp_path: Path) -> None:
    candidate = tmp_path / "do_nothing.py"
    candidate.write_text(
        '''
def solve(case, max_sim_calls=0, simulate_fn=None):
    return {"actions": [0.0] * int(case["number_of_ports"])}
''',
        encoding="utf-8",
    )
    metrics = _run_ev2gym(candidate, tmp_path)
    assert metrics["combined_score"] <= EV2GYM_BASELINE_SCORE


@ev2gym_installed
def test_ev2gym_crashing_candidate_is_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "boom.py"
    candidate.write_text(
        "def solve(case, max_sim_calls=0, simulate_fn=None):\n"
        "    raise RuntimeError('boom')\n",
        encoding="utf-8",
    )
    metrics = _run_ev2gym(candidate, tmp_path)
    assert metrics["valid"] == 0.0


# --------------------------------------------------------------------------
# 4. SustainableDataCenterControl -- the poisoned-yardstick benchmark
# --------------------------------------------------------------------------


def _sustaindc_root() -> Path | None:
    """Locate a usable dc-rl checkout, or None (it is not vendored in-repo)."""
    env_root = (os.environ.get("SUSTAINDC_ROOT") or "").strip()
    candidates = [Path(env_root)] if env_root else []
    candidates.append(SUSTAINDC_DIR / "sustaindc")
    for root in candidates:
        if (root / "sustaindc_env.py").is_file():
            return root.resolve()
    return None


needs_sustaindc = pytest.mark.skipif(
    _sustaindc_root() is None,
    reason="no dc-rl checkout (set SUSTAINDC_ROOT or vendor sustaindc/)",
)


# --- Structural assertions: these need no simulator at all ------------------


def test_sdc_evaluator_never_imports_the_candidate() -> None:
    """`verification/evaluate.py` must not exec candidate code in-process."""
    source = (SUSTAINDC_DIR / "verification" / "evaluate.py").read_text(encoding="utf-8")
    assert "run_benchmark_isolated" in source
    # The in-process loader must not be used on the candidate any more.
    assert "load_policy_module" not in source
    assert "policy_module = " not in source


def test_sdc_core_exposes_the_isolated_path() -> None:
    source = (SUSTAINDC_DIR / "benchmark_core.py").read_text(encoding="utf-8")
    assert "class IsolatedPolicy" in source
    assert "def run_benchmark_isolated" in source
    assert (SUSTAINDC_DIR / "verification" / "policy_runner.py").is_file()


def test_sdc_policy_runner_is_protected_and_shipped() -> None:
    """The trusted child driver must be copied into the sandbox and readonly."""
    fe = SUSTAINDC_DIR / "frontier_eval"
    copy_files = (fe / "copy_files.txt").read_text(encoding="utf-8").split()
    readonly = (fe / "readonly_files.txt").read_text(encoding="utf-8").split()
    assert "verification/policy_runner.py" in copy_files
    assert "verification/policy_runner.py" in readonly


def _import_benchmark_core():
    sys.path.insert(0, str(SUSTAINDC_DIR))
    try:
        import benchmark_core  # noqa: PLC0415

        return benchmark_core
    finally:
        sys.path.pop(0)


def test_sdc_noop_reference_comes_from_the_core_module() -> None:
    """The yardstick must be this module's own class, not anything injected."""
    core = _import_benchmark_core()
    assert core.NoOpPolicy.__module__ == "benchmark_core"
    assert core.NoOpPolicy.decide_actions({}) == {
        "agent_ls": 1,
        "agent_dc": 1,
        "agent_bat": 2,
    }
    # SCENARIOS is a scoring input, so it is immutable.
    assert isinstance(core.SCENARIOS, tuple)


def test_sdc_integrity_check_catches_scoring_input_tampering() -> None:
    """Every global the relative score depends on is pinned."""
    core = _import_benchmark_core()
    core._assert_scoring_integrity()  # baseline: clean

    class Rigged:
        @staticmethod
        def decide_actions(observations):
            return {"agent_ls": 2, "agent_dc": 0, "agent_bat": 0}

    for attr, bad_value in [
        ("NoOpPolicy", Rigged),
        ("NOISE_TOLERANCE", 0.9),
        ("SCENARIOS", core.SCENARIOS[:1]),
        ("BENCHMARK_ENV_CONFIG", {"agents": []}),
    ]:
        original = getattr(core, attr)
        setattr(core, attr, bad_value)
        try:
            with pytest.raises(RuntimeError):
                core._assert_scoring_integrity()
        finally:
            setattr(core, attr, original)
    core._assert_scoring_integrity()  # restored


def test_sdc_stale_frozen_reference_is_not_trusted(tmp_path: Path) -> None:
    """A frozen NoOp table with the wrong fingerprint must be ignored, not used."""
    core = _import_benchmark_core()
    fake_root = tmp_path / "fake_sustaindc"
    fake_root.mkdir()
    (fake_root / "sustaindc_env.py").write_text("# stub\n", encoding="utf-8")

    original_path = core.NOOP_REFERENCE_PATH
    table = tmp_path / "noop_reference.json"
    table.write_text(
        json.dumps(
            {
                "fingerprint": "0" * 64,
                "episodes": {
                    s.name: {"scenario": s.name, "carbon_kg": 1e12, "water_l": 1e12}
                    for s in core.SCENARIOS
                },
            }
        ),
        encoding="utf-8",
    )
    core.NOOP_REFERENCE_PATH = table
    try:
        assert core.load_noop_reference(fake_root) is None
    finally:
        core.NOOP_REFERENCE_PATH = original_path


# --- Functional assertions: need a dc-rl checkout ---------------------------


def _run_sustaindc(candidate: Path, tmp_path: Path) -> dict:
    root = _sustaindc_root()
    metrics = tmp_path / "metrics.json"
    proc = _run(
        [
            sys.executable,
            SUSTAINDC_DIR / "verification" / "evaluate.py",
            "--solution",
            candidate,
            "--sustaindc-root",
            root,
            "--save-json",
            tmp_path / "last_eval.json",
            "--metrics-out",
            metrics,
            "--artifacts-out",
            tmp_path / "artifacts.json",
        ],
        cwd=SUSTAINDC_DIR,
    )
    assert metrics.is_file(), f"no metrics written: {proc.stderr[-3000:]}"
    return _read_metrics(metrics)


# The simulator is not bit-reproducible run to run (identical NoOp policies in
# identical fresh processes differ by ~0.02% on carbon), so the honest score is
# asserted as a band rather than an exact value. Measured spread over six runs
# of the honest baseline, in-process and isolated: 8.367 .. 8.445.
SDC_HONEST_SCORE_RANGE = (7.5, 9.5)


@needs_sustaindc
@pytest.mark.slow
def test_sdc_honest_baseline_scores_in_band(tmp_path: Path) -> None:
    metrics = _run_sustaindc(SUSTAINDC_DIR / "baseline" / "solution.py", tmp_path)
    assert metrics["valid"] == 1.0
    low, high = SDC_HONEST_SCORE_RANGE
    assert low <= metrics["combined_score"] <= high


@needs_sustaindc
@pytest.mark.slow
def test_sdc_poisoning_the_noop_reference_no_longer_works(tmp_path: Path) -> None:
    """The archived exploit: degrade the yardstick instead of improving.

    Against the old in-process evaluator this exact file scored 99.95 while
    behaving identically to NoOp. It must now score ~0.
    """
    candidate = tmp_path / "poison_reference.py"
    candidate.write_text(
        '''
import sys

_core = sys.modules.get("benchmark_core")
if _core is not None:
    _real_run_episode = _core.run_episode
    _NoOp = _core.NoOpPolicy

    def _rigged(policy_module, scenario, sustaindc_root=None):
        m = _real_run_episode(policy_module, scenario, sustaindc_root=sustaindc_root)
        if policy_module is _NoOp or policy_module is _core.NoOpPolicy:
            m.carbon_kg *= 1000.0
            m.water_l *= 1000.0
        return m

    _core.run_episode = _rigged
    _core.NOISE_TOLERANCE = -1.0

    class _Wasteful:
        @staticmethod
        def reset_policy():
            return None

        @staticmethod
        def decide_actions(observations):
            return {"agent_ls": 2, "agent_dc": 0, "agent_bat": 0}

    _core.NoOpPolicy = _Wasteful

for _name in ("__main__", "evaluate"):
    _main = sys.modules.get(_name)
    if _main is not None and hasattr(_main, "run_benchmark_isolated"):
        _main.run_benchmark_isolated = lambda *a, **k: {
            "average_score": 100.0,
            "score_ceiling": 100.0,
            "scenario_reports": [],
            "candidate_aggregate": {},
            "noop_aggregate": {},
        }


def reset_policy():
    return None


def decide_actions(observations):
    # Byte-identical to the NoOp policy: zero genuine improvement.
    return {"agent_ls": 1, "agent_dc": 1, "agent_bat": 2}
''',
        encoding="utf-8",
    )
    metrics = _run_sustaindc(candidate, tmp_path)
    assert metrics["combined_score"] < 1.0, (
        "candidate poisoned its own reference: " f"{metrics['combined_score']}"
    )


@needs_sustaindc
def test_sdc_invalid_action_is_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "bad_action.py"
    candidate.write_text(
        "def decide_actions(observations):\n"
        "    return {'agent_ls': 7, 'agent_dc': 1, 'agent_bat': 2}\n",
        encoding="utf-8",
    )
    metrics = _run_sustaindc(candidate, tmp_path)
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == 0.0


@needs_sustaindc
def test_sdc_crashing_candidate_is_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "boom.py"
    candidate.write_text(
        "def decide_actions(observations):\n    raise RuntimeError('boom')\n",
        encoding="utf-8",
    )
    metrics = _run_sustaindc(candidate, tmp_path)
    assert metrics["valid"] == 0.0


@needs_sustaindc
@pytest.mark.slow
def test_sdc_chatty_candidate_does_not_deadlock(tmp_path: Path) -> None:
    """Child stdio must not go to an undrained pipe.

    The parent only reads the dedicated response pipe during the step loop, so
    routing the child's stdout/stderr to a pipe would let a noisy candidate fill
    the 64K buffer and hang until the wall-clock budget expired.
    """
    candidate = tmp_path / "chatty.py"
    candidate.write_text(
        '''
import sys

_NOISE = "x" * 4096


def decide_actions(observations):
    for _ in range(64):
        print(_NOISE)
        print(_NOISE, file=sys.stderr)
    return {"agent_ls": 1, "agent_dc": 1, "agent_bat": 2}
''',
        encoding="utf-8",
    )
    # >32MB of child output across the run; must still complete and score.
    metrics = _run_sustaindc(candidate, tmp_path)
    assert metrics["valid"] == 1.0
    assert "candidate_error" not in metrics
