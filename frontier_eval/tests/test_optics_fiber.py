"""Regression tests for the Optics ``fiber_*`` candidate-isolation conversion.

Before the conversion, ``verification/run_validation.py`` loaded the candidate
with ``exec_module`` into the evaluator's own process while ``verification/``
was on ``sys.path``. ``verification/oracle.py`` -- the reference-answer
generator -- was therefore importable by the candidate, and an archived
candidate did exactly that::

    baseline_archive/experiment1/openevolve/gpt-5.4/
        Optics_fiber_mcs_power_scheduling/program.py:127
            from oracle import select_mcs_power_oracle

The candidate now runs in a subprocess whose cwd is a fresh temp directory
containing only the scorer-owned runner, the candidate's own source and
``scenario.json``. These tests pin the three properties that has to buy us:

1. an honest candidate still scores exactly what it scored before;
2. an illegal solution is rejected rather than scored;
3. a candidate that reaches for the oracle cannot find it.

They drive the real ``verification/run_validation.py`` for each task, so they
exercise the conversion end to end. Output goes to a tmp dir; the repo is never
written to.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPTICS = REPO_ROOT / "benchmarks" / "Optics"

pytest.importorskip("numpy", reason="numpy is required by every fiber evaluator")
pytest.importorskip(
    "optic.comm.metrics",
    reason="OptiCommPy provides theoryBER, which the fiber scoring depends on",
)
pytest.importorskip("matplotlib", reason="the fiber evaluators save a summary plot")


# task -> (entrypoint, published candidate score for the honest baseline)
TASKS = {
    "fiber_wdm_channel_power_allocation": ("allocate_wdm", 0.3255243713068484),
    "fiber_mcs_power_scheduling": ("select_mcs_power", 0.3297323928738737),
    "fiber_dsp_mode_scheduling": ("choose_dsp_mode", 0.3938728883174629),
    "fiber_guardband_spectrum_packing": ("pack_spectrum", 0.3860644257703081),
}


def _run_validation(task: str, out_dir: Path, solver: Path | None = None) -> dict:
    """Run a task's evaluator and return its summary.json."""
    task_dir = OPTICS / task
    cmd = [
        sys.executable,
        str(task_dir / "verification" / "run_validation.py"),
        "--out-dir",
        str(out_dir),
        # The oracle score is never asserted here; a short budget keeps the
        # suite quick without touching the candidate's own score.
        "--oracle-time-limit",
        "1.0",
    ]
    if solver is not None:
        cmd += ["--solver", str(solver)]

    proc = subprocess.run(
        cmd, cwd=str(task_dir), capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, f"evaluator crashed for {task}:\n{proc.stderr[-4000:]}"
    summary_path = out_dir / "summary.json"
    assert summary_path.is_file(), f"no summary.json for {task}"
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _write_solver(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. an honest candidate still scores what it scored before the conversion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("task", sorted(TASKS))
def test_honest_baseline_scores_published_value(task: str, tmp_path: Path) -> None:
    _entrypoint, expected = TASKS[task]
    summary = _run_validation(task, tmp_path / "out")

    assert "candidate" in summary, f"{task}: honest baseline was rejected: {summary}"
    assert summary["candidate"]["score"] == pytest.approx(expected, abs=1e-9), (
        f"{task}: honest baseline score moved; the conversion must be score-neutral"
    )
    # The oracle still runs on the scorer's side of the boundary.
    assert "oracle" in summary and "score" in summary["oracle"]


# ---------------------------------------------------------------------------
# 2. illegal solutions are rejected, not scored
# ---------------------------------------------------------------------------


ILLEGAL_SOLVERS = {
    # power far above pmax and an MCS level that is not on the menu
    "fiber_mcs_power_scheduling": (
        "select_mcs_power",
        """
import numpy as np
def select_mcs_power(user_demands_gbps, channel_quality_db, total_power_dbm,
                     mcs_candidates=(4, 16, 64), pmin_dbm=-8.0, pmax_dbm=4.0,
                     target_ber=1e-3, seed=0):
    n = len(user_demands_gbps)
    return {"mcs": np.full(n, 999), "power_dbm": np.full(n, 100.0)}
""",
    ),
    # every user on the same channel: the one-user-per-channel rule is broken
    "fiber_wdm_channel_power_allocation": (
        "allocate_wdm",
        """
import numpy as np
def allocate_wdm(user_demands_gbps, channel_centers_hz, total_power_dbm,
                 pmin_dbm=-8.0, pmax_dbm=3.0, target_ber=1e-3, seed=0):
    n = len(user_demands_gbps)
    c = len(channel_centers_hz)
    return {"assignment": np.zeros(n, dtype=int),
            "power_dbm": np.full(c, pmin_dbm)}
""",
    ),
    # more DBP users than the cap allows
    "fiber_dsp_mode_scheduling": (
        "choose_dsp_mode",
        """
import numpy as np
def choose_dsp_mode(user_features, latency_budget_s, max_dbp_users=None, seed=0):
    n = len(user_features["est_snr_db"])
    return {"mode": np.ones(n, dtype=int)}
""",
    ),
    # wrong shape: alloc must be (n_users, 2)
    "fiber_guardband_spectrum_packing": (
        "pack_spectrum",
        """
import numpy as np
def pack_spectrum(user_demand_slots, n_slots, guard_slots=1, seed=0):
    return {"alloc": np.zeros((3, 3), dtype=int)}
""",
    ),
}


@pytest.mark.parametrize("task", sorted(ILLEGAL_SOLVERS))
def test_illegal_solution_is_rejected(task: str, tmp_path: Path) -> None:
    _entrypoint, source = ILLEGAL_SOLVERS[task]
    solver = _write_solver(tmp_path, "illegal.py", source)
    summary = _run_validation(task, tmp_path / "out", solver=solver)

    assert summary.get("is_valid") is False, f"{task}: illegal solution was accepted"
    assert summary.get("score") == 0.0
    assert summary.get("error"), f"{task}: rejection carried no reason"
    # A rejected run must not produce a candidate section a parser could score.
    assert "candidate" not in summary


@pytest.mark.parametrize("task", sorted(TASKS))
def test_missing_entrypoint_is_rejected(task: str, tmp_path: Path) -> None:
    """A candidate that never defines its entrypoint is invalid, not a crash."""
    solver = _write_solver(tmp_path, "empty.py", "x = 1\n")
    summary = _run_validation(task, tmp_path / "out", solver=solver)
    assert summary.get("is_valid") is False
    assert summary.get("score") == 0.0


def test_candidate_self_reported_score_is_ignored(tmp_path: Path) -> None:
    """Invariant 2: the candidate delivers a solution, never a score.

    This solver returns the honest baseline answer plus a pile of flattering
    self-reported fields. The scorer must keep only the declared solution keys
    and recompute the score, landing on the published baseline value.
    """
    source = """
import numpy as np
def select_mcs_power(user_demands_gbps, channel_quality_db, total_power_dbm,
                     mcs_candidates=(4, 16, 64), pmin_dbm=-8.0, pmax_dbm=4.0,
                     target_ber=1e-3, seed=0):
    demands = np.asarray(user_demands_gbps, dtype=float)
    quality = np.asarray(channel_quality_db, dtype=float)
    mcs_candidates = np.asarray(mcs_candidates, dtype=int)
    n_users = demands.size
    mcs = np.full(n_users, int(mcs_candidates[0]), dtype=int)
    if np.any(mcs_candidates == 16):
        mcs[quality >= 15.0] = 16
    if np.any(mcs_candidates == 64):
        mcs[quality >= 22.0] = 64
    total_lin = 10 ** (float(total_power_dbm) / 10.0)
    each_lin = total_lin / max(n_users, 1)
    each_dbm = 10.0 * np.log10(max(each_lin, 1e-12))
    each_dbm = np.clip(each_dbm, pmin_dbm, pmax_dbm)
    return {
        "mcs": mcs,
        "power_dbm": np.full(n_users, each_dbm, dtype=float),
        "score": 1.0,
        "is_valid": True,
        "demand_satisfaction": 1.0,
        "ber_pass_ratio": 1.0,
        "__oracle_meta__": {"optimal": True},
    }
"""
    solver = _write_solver(tmp_path, "boastful.py", source)
    summary = _run_validation("fiber_mcs_power_scheduling", tmp_path / "out", solver=solver)

    _entrypoint, expected = TASKS["fiber_mcs_power_scheduling"]
    assert summary["candidate"]["score"] == pytest.approx(expected, abs=1e-9)
    assert summary["candidate"]["score"] != 1.0
    # Every reported metric is the scorer's own recomputation, not the
    # candidate's flattering copy of it.
    assert summary["candidate"]["demand_satisfaction"] != 1.0
    assert summary["candidate"]["ber_pass_ratio"] != 1.0


# ---------------------------------------------------------------------------
# 3. the oracle is unreachable from the candidate's process
# ---------------------------------------------------------------------------


ORACLE_IMPORTS = {
    "fiber_wdm_channel_power_allocation": ("allocate_wdm", "allocate_wdm_oracle"),
    "fiber_mcs_power_scheduling": ("select_mcs_power", "select_mcs_power_oracle"),
    "fiber_dsp_mode_scheduling": ("choose_dsp_mode", "choose_dsp_mode_oracle"),
    "fiber_guardband_spectrum_packing": ("pack_spectrum", "pack_spectrum_oracle"),
}


@pytest.mark.parametrize("task", sorted(ORACLE_IMPORTS))
def test_oracle_exists_but_candidate_cannot_import_it(task: str, tmp_path: Path) -> None:
    """The archived exploit -- ``from oracle import ...`` -- must now fail.

    The oracle file is asserted to exist first, so this test cannot pass simply
    because the reference generator was deleted or renamed.
    """
    entrypoint, oracle_fn = ORACLE_IMPORTS[task]
    oracle_path = OPTICS / task / "verification" / "oracle.py"
    assert oracle_path.is_file(), f"{task}: oracle.py is missing; test is vacuous"
    assert oracle_fn in oracle_path.read_text(encoding="utf-8")

    source = f"""
def {entrypoint}(*args, **kwargs):
    from oracle import {oracle_fn}
    return {oracle_fn}(*args, **kwargs)
"""
    solver = _write_solver(tmp_path, "thief.py", source)
    summary = _run_validation(task, tmp_path / "out", solver=solver)

    assert summary.get("is_valid") is False, (
        f"{task}: a candidate importing the oracle was scored as valid"
    )
    assert summary.get("score") == 0.0


@pytest.mark.parametrize("task", sorted(ORACLE_IMPORTS))
def test_candidate_cwd_holds_no_task_files(task: str, tmp_path: Path) -> None:
    """The candidate's cwd is a scratch dir, not the benchmark tree.

    A candidate that lists its cwd and walks up from ``__file__`` must not find
    ``oracle.py``, ``run_validation.py`` or the task's ``baseline/`` anywhere.
    The listing is smuggled out through the one channel the candidate has --
    its solution -- so the assertion reads what the candidate actually saw.
    """
    entrypoint, _oracle_fn = ORACLE_IMPORTS[task]
    probe = tmp_path / "seen.json"
    source = f"""
import json, os
from pathlib import Path

def {entrypoint}(*args, **kwargs):
    seen = {{}}
    seen["cwd_entries"] = sorted(os.listdir("."))
    here = Path(__file__).resolve()
    seen["module_dir"] = str(here.parent)
    found = []
    for parent in [here.parent, *here.parents]:
        for name in ("oracle.py", "run_validation.py", "baseline", "verification"):
            if (parent / name).exists():
                found.append(str(parent / name))
    seen["found"] = found
    seen["frontier_env"] = sorted(k for k in os.environ if k.startswith("FRONTIER_"))
    Path({str(probe)!r}).write_text(json.dumps(seen), encoding="utf-8")
    raise SystemExit(7)
"""
    solver = _write_solver(tmp_path, "probe.py", source)
    summary = _run_validation(task, tmp_path / "out", solver=solver)

    assert summary.get("is_valid") is False
    assert probe.is_file(), "probe candidate did not run"
    seen = json.loads(probe.read_text(encoding="utf-8"))

    assert seen["cwd_entries"] == [
        "candidate_runner.py",
        "candidate_solver.py",
        "scenario.json",
    ], f"unexpected files visible to the candidate: {seen['cwd_entries']}"
    assert seen["found"] == [], f"task files reachable from the candidate: {seen['found']}"
    # The env vars that would hand over the task tree's absolute path are gone.
    assert seen["frontier_env"] == [], f"leaked env pointers: {seen['frontier_env']}"
