"""Regression tests for the three PyPortfolioOpt tasks.

Two holes were closed in this benchmark group and both are covered here.

**A. The risk constraints could be erased.** Each evaluator ran the candidate
with ``exec_module`` in the scoring process, and every constraint (budget,
per-asset bounds, sector limits, turnover cap, factor exposure) was enforced
only inside a single ``_feasibility_penalty`` helper that was looked up by name
at scoring time. A candidate needed one module-level line --
``sys.modules['__main__']._feasibility_penalty = lambda *a: 0.0`` -- to zero
every financial control, then solve an unconstrained problem for 100/100. The
candidate now runs in a subprocess; the scorer retains the original
``(1 - penalty)`` multiplier and computes it independently.

**B. The oracle was readable.** ``verification/reference.py`` was listed in
``agent_files.txt`` and copied into the sandbox by ``copy_files.txt: .``, so a
candidate could import it and return its answer for a free 100/100 without
tripping the readonly check. The reference optimum is now a precomputed
constant table and the module is neither shipped nor executed at scoring time.

These tests drive each task's ``verification/evaluate.py`` directly. They never
mutate the repository: the candidate is always passed as an explicit path.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GROUP_DIR = REPO_ROOT / "benchmarks" / "PyPortfolioOpt"

try:  # the honest-solution tests need a convex solver
    import cvxpy  # noqa: F401

    HAVE_CVXPY = True
except Exception:  # pragma: no cover - environment dependent
    HAVE_CVXPY = False

requires_cvxpy = pytest.mark.skipif(not HAVE_CVXPY, reason="cvxpy is not installed")


# ---------------------------------------------------------------------------
# Candidate programs used by the tests.
# ---------------------------------------------------------------------------

#: Problem A, as an archived-style exploit: neutralise the penalty hook wherever
#: it can be reached, then return a solution that ignores every constraint.
EXPLOIT_ERASE_CONSTRAINTS = '''
import sys
import numpy as np

_NEUTRALISED = []
for _name, _mod in list(sys.modules.items()):
    for _attr in ("_feasibility_penalty", "check_feasibility", "constraint_residuals",
                  "constraint_tolerances"):
        try:
            if hasattr(_mod, _attr):
                if _attr == "_feasibility_penalty":
                    setattr(_mod, _attr, lambda *a, **k: 0.0)
                elif _attr == "check_feasibility":
                    setattr(_mod, _attr, lambda *a, **k: (True, [], {}))
                else:
                    setattr(_mod, _attr, lambda *a, **k: {})
                _NEUTRALISED.append("%s.%s" % (_name, _attr))
        except Exception:
            pass


def solve_instance(instance):
__BODY__
'''

#: Problem B: reach the oracle on disk and hand back its answer verbatim.
EXPLOIT_IMPORT_ORACLE = '''
import importlib.util
import os
from pathlib import Path

_ref = None
for _p in [Path(__file__).resolve().parent] + list(Path(__file__).resolve().parents):
    _c = (_p / "verification" / "reference.py").resolve()
    if _c.is_file():
        _s = importlib.util.spec_from_file_location("oracle", str(_c))
        _ref = importlib.util.module_from_spec(_s)
        _s.loader.exec_module(_ref)
        break

_LEAKED_ENV = sorted(k for k in os.environ if k.startswith("FRONTIER"))


def solve_instance(instance):
    if _ref is None:
        raise RuntimeError("oracle unreachable; FRONTIER* env seen: %r" % (_LEAKED_ENV,))
    return _ref.solve_instance(instance)
'''


@dataclass(frozen=True)
class TaskSpec:
    name: str
    solution_key: str          # "weights" or "lots"
    objective_key: str         # row field holding the candidate's objective
    reference_key: str         # row field holding the reference objective
    baseline_score: float      # published score of the shipped baseline
    honest_source: str         # a genuine solver, expected to score 100
    slack_source: str          # honest solver, one limit relaxed by 1%
    unconstrained_body: str    # body for EXPLOIT_ERASE_CONSTRAINTS

    @property
    def dir(self) -> Path:
        return GROUP_DIR / self.name

    @property
    def evaluator(self) -> Path:
        return self.dir / "verification" / "evaluate.py"


_MVO_SOLVER = '''
import cvxpy as cp
import numpy as np


def _solve(instance, turnover_scale=1.0):
    mu = np.asarray(instance["mu"], dtype=float)
    cov = np.asarray(instance["cov"], dtype=float)
    w_prev = np.asarray(instance["w_prev"], dtype=float)
    lower = np.asarray(instance["lower"], dtype=float)
    upper = np.asarray(instance["upper"], dtype=float)
    sector_ids = np.asarray(instance["sector_ids"], dtype=int)
    fl = np.asarray(instance["factor_loadings"], dtype=float)
    n = mu.size
    w = cp.Variable(n)
    obj = cp.Maximize(
        mu @ w
        - float(instance["risk_aversion"]) * cp.quad_form(w, cov)
        - float(instance["transaction_penalty"]) * cp.norm1(w - w_prev)
    )
    cons = [
        cp.sum(w) == 1,
        w >= lower,
        w <= upper,
        cp.norm1(w - w_prev) <= float(instance["turnover_limit"]) * turnover_scale,
        fl.T @ w >= np.asarray(instance["factor_lower"], dtype=float),
        fl.T @ w <= np.asarray(instance["factor_upper"], dtype=float),
    ]
    for s, lo in instance["sector_lower"].items():
        cons.append(cp.sum(w[np.where(sector_ids == int(s))[0]]) >= float(lo))
    for s, hi in instance["sector_upper"].items():
        cons.append(cp.sum(w[np.where(sector_ids == int(s))[0]]) <= float(hi))
    prob = cp.Problem(obj, cons)
    for solver in [cp.SCS, cp.ECOS, cp.OSQP]:
        try:
            prob.solve(solver=solver, verbose=False)
            if prob.status in {"optimal", "optimal_inaccurate"}:
                break
        except Exception:
            continue
    return {"weights": np.asarray(w.value).reshape(-1)}
'''

_CVAR_SOLVER = '''
import cvxpy as cp
import numpy as np


def _solve(instance, turnover_scale=1.0):
    R = np.asarray(instance["scenario_returns"], dtype=float)
    mu = np.asarray(instance["mu"], dtype=float)
    w_prev = np.asarray(instance["w_prev"], dtype=float)
    lower = np.asarray(instance["lower"], dtype=float)
    upper = np.asarray(instance["upper"], dtype=float)
    sector_ids = np.asarray(instance["sector_ids"], dtype=int)
    beta = float(instance["beta"])
    T, n = R.shape
    w = cp.Variable(n)
    alpha = cp.Variable()
    u = cp.Variable(T)
    z = cp.Variable(n)
    cons = [
        cp.sum(w) == 1,
        w >= lower,
        w <= upper,
        mu @ w >= float(instance["target_return"]),
        u >= 0,
        u >= -R @ w - alpha,
        z >= w - w_prev,
        z >= -(w - w_prev),
        z >= 0,
        cp.sum(z) <= float(instance["turnover_limit"]) * turnover_scale,
    ]
    for s, lo in instance["sector_lower"].items():
        cons.append(cp.sum(w[np.where(sector_ids == int(s))[0]]) >= float(lo))
    for s, hi in instance["sector_upper"].items():
        cons.append(cp.sum(w[np.where(sector_ids == int(s))[0]]) <= float(hi))
    prob = cp.Problem(
        cp.Minimize(alpha + (1.0 / ((1.0 - beta) * T)) * cp.sum(u)), cons
    )
    for solver in [cp.SCS, cp.ECOS, cp.OSQP]:
        try:
            prob.solve(solver=solver, verbose=False)
            if prob.status in {"optimal", "optimal_inaccurate"}:
                break
        except Exception:
            continue
    return {"weights": np.asarray(w.value).reshape(-1)}
'''

_MIP_SOLVER = '''
import cvxpy as cp
import numpy as np


def _solve(instance, turnover_scale=1.0):
    prices = np.asarray(instance["prices"], dtype=float)
    lot_sizes = np.asarray(instance["lot_sizes"], dtype=float)
    current_lots = np.asarray(instance["current_lots"], dtype=float)
    target_weights = np.asarray(instance["target_weights"], dtype=float)
    pv = float(instance["portfolio_value"])
    fee = float(instance["fee_rate"])
    tl = float(instance["turnover_limit_value"]) * turnover_scale
    max_lots = np.asarray(instance["max_lots"], dtype=float)
    unit = prices * lot_sizes
    target_dollar = target_weights * pv
    n = unit.size
    x = cp.Variable(n, integer=True)
    u = cp.Variable(n)
    v = cp.Variable(n)
    traded = cp.sum(cp.multiply(unit, v))
    cons = [
        x >= 0,
        x <= max_lots,
        u >= cp.multiply(unit, x) - target_dollar,
        u >= -(cp.multiply(unit, x) - target_dollar),
        u >= 0,
        v >= x - current_lots,
        v >= -(x - current_lots),
        v >= 0,
        traded <= tl,
        cp.sum(cp.multiply(unit, x)) + fee * traded <= pv,
    ]
    prob = cp.Problem(cp.Minimize(cp.sum(u) + fee * traded), cons)
    prob.solve(solver=cp.HIGHS, verbose=False)
    return {"lots": np.rint(np.asarray(x.value).reshape(-1)).astype(int)}
'''

_HONEST = "\n\ndef solve_instance(instance):\n    return _solve(instance, 1.0)\n"
#: A 1% looser turnover cap. Under the old soft penalty this bought objective
#: for a few points of penalty -- the "breach the limit slightly, it barely
#: costs anything" arbitrage. Under the hard gate it is worth zero.
_SLACK = "\n\ndef solve_instance(instance):\n    return _solve(instance, 1.01)\n"

TASKS = [
    TaskSpec(
        name="robust_mvo_rebalance",
        solution_key="weights",
        objective_key="f_cand",
        reference_key="f_ref",
        baseline_score=32.9827451572,
        honest_source=_MVO_SOLVER + _HONEST,
        slack_source=_MVO_SOLVER + _SLACK,
        unconstrained_body=(
            "    mu = np.asarray(instance['mu'], dtype=float)\n"
            "    cov = np.asarray(instance['cov'], dtype=float)\n"
            "    ra = float(instance['risk_aversion'])\n"
            "    return {'weights': np.linalg.solve(2.0 * ra * cov, mu)}\n"
        ),
    ),
    TaskSpec(
        name="cvar_stress_control",
        solution_key="weights",
        objective_key="c_cand",
        reference_key="c_ref",
        baseline_score=17.9236979407,
        honest_source=_CVAR_SOLVER + _HONEST,
        slack_source=_CVAR_SOLVER + _SLACK,
        unconstrained_body=(
            "    R = np.asarray(instance['scenario_returns'], dtype=float)\n"
            "    beta = float(instance['beta'])\n"
            "    losses = -R\n"
            "    q = np.quantile(losses, beta, axis=0)\n"
            "    tail = np.array([losses[losses[:, j] >= q[j], j].mean()\n"
            "                     for j in range(R.shape[1])])\n"
            "    w = np.zeros(R.shape[1])\n"
            "    w[int(np.argmin(tail))] = 1.0\n"
            "    return {'weights': w}\n"
        ),
    ),
    TaskSpec(
        name="discrete_rebalance_mip",
        solution_key="lots",
        objective_key="obj_cand",
        reference_key="obj_ref",
        baseline_score=37.4950984992,
        honest_source=_MIP_SOLVER + _HONEST,
        slack_source=_MIP_SOLVER + _SLACK,
        unconstrained_body=(
            "    unit = (np.asarray(instance['prices'], dtype=float)\n"
            "            * np.asarray(instance['lot_sizes'], dtype=float))\n"
            "    td = (np.asarray(instance['target_weights'], dtype=float)\n"
            "          * float(instance['portfolio_value']))\n"
            "    x = np.rint(td / np.maximum(unit, 1e-12))\n"
            "    x = np.minimum(np.maximum(x, 0),\n"
            "                   np.asarray(instance['max_lots'], dtype=float))\n"
            "    return {'lots': x.astype(int)}\n"
        ),
    ),
]

TASK_IDS = [t.name for t in TASKS]


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------
def _run_evaluator(
    spec: TaskSpec,
    candidate: Path,
    *,
    cwd: Path | None = None,
    repo_root: Path | None = None,
) -> dict:
    """Run a task evaluator on `candidate` and return (metrics, artifacts).

    ``repo_root`` sets FRONTIER_ENGINEERING_ROOT the way the unified harness
    does (evaluator/python.py sets it to spec.repo_root). The evaluator needs
    it to locate benchmarks/_shared/candidate_sandbox.py; without it a sandbox
    run fails on the import rather than on the thing under test.
    """
    with tempfile.TemporaryDirectory() as tmp:
        metrics_path = Path(tmp) / "metrics.json"
        artifacts_path = Path(tmp) / "artifacts.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(spec.evaluator if cwd is None else cwd / "verification" / "evaluate.py"),
                str(candidate),
                "--metrics-out",
                str(metrics_path),
                "--artifacts-out",
                str(artifacts_path),
            ],
            cwd=str(cwd or spec.dir),
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "FRONTIER_ENGINEERING_ROOT": str(repo_root)}
            if repo_root is not None
            else None,
        )
        assert proc.returncode == 0, f"evaluator crashed:\n{proc.stderr[-3000:]}"
        return {
            "metrics": json.loads(metrics_path.read_text(encoding="utf-8")),
            "artifacts": json.loads(artifacts_path.read_text(encoding="utf-8")),
            "stdout": proc.stdout,
        }


def _write_candidate(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "candidate.py"
    path.write_text(source, encoding="utf-8")
    return path


def _read_list_file(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


# ---------------------------------------------------------------------------
# 1. Honest solutions keep their score.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
def test_shipped_baseline_scores_published_value(spec: TaskSpec) -> None:
    """The shipped heuristic keeps its published score and is fully feasible."""
    result = _run_evaluator(spec, spec.dir / "baseline" / "init.py")
    metrics = result["metrics"]
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == pytest.approx(spec.baseline_score, abs=0.05)


@requires_cvxpy
@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
def test_honest_convex_solution_scores_100(spec: TaskSpec, tmp_path: Path) -> None:
    """An honest solver of the *same* program still scores 100/100.

    Numerical solver residuals retain the original small soft penalty, so
    an approximate convex solution need not score exactly 100.
    """
    candidate = _write_candidate(tmp_path, spec.honest_source)
    result = _run_evaluator(spec, candidate)
    metrics = result["metrics"]
    assert metrics["num_infeasible_instances"] == 0.0
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == pytest.approx(100.0, abs=0.01)


@requires_cvxpy
@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
def test_honest_solution_leaves_slack_against_tolerances(
    spec: TaskSpec, tmp_path: Path
) -> None:
    """Every honest residual sits well inside its tolerance, not at the edge."""
    candidate = _write_candidate(tmp_path, spec.honest_source)
    result = _run_evaluator(spec, candidate)
    tolerances = result["artifacts"]["constraint_tolerances"]
    for row in result["artifacts"]["rows"]:
        per_instance = (
            tolerances
            if "budget" in tolerances or "integrality" in tolerances
            else tolerances[str(row["seed"])]
        )
        for name, residual in row["residuals"].items():
            tol = float(per_instance[name])
            assert residual <= 0.5 * tol, (
                f"{spec.name} seed={row['seed']} {name}: residual {residual:.3e} "
                f"is more than half of tolerance {tol:.3e}"
            )


# ---------------------------------------------------------------------------
# 2. Risk-constraint violations score 0 rather than losing a slice.
# ---------------------------------------------------------------------------
@requires_cvxpy
@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
def test_slightly_relaxed_limit_receives_the_original_soft_penalty(
    spec: TaskSpec, tmp_path: Path
) -> None:
    """Small constraint breaches retain the documented soft deduction."""
    candidate = _write_candidate(tmp_path, spec.slack_source)
    result = _run_evaluator(spec, candidate)
    metrics = result["metrics"]
    rows = result["artifacts"]["rows"]

    assert metrics["num_infeasible_instances"] > 0
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] == pytest.approx(sum(r["score"] for r in rows) / len(rows))
    breached = [r for r in rows if not r["feasible"]]
    assert breached
    for row in breached:
        assert row["penalty"] > 0
        assert row["score"] == pytest.approx(100 * row["norm"] * (1 - row["penalty"]))

    # It is genuinely a *better* objective -- that is the point of the test.
    better = [
        r
        for r in breached
        if (
            r[spec.objective_key] > r[spec.reference_key]
            if spec.name == "robust_mvo_rebalance"
            else r[spec.objective_key] < r[spec.reference_key]
        )
    ]
    assert better, "relaxing the cap should improve the objective on some seed"


@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
def test_erasing_the_penalty_hook_no_longer_helps(
    spec: TaskSpec, tmp_path: Path
) -> None:
    """The candidate cannot erase the scorer's original penalty function."""
    source = EXPLOIT_ERASE_CONSTRAINTS.replace(
        "__BODY__\n", spec.unconstrained_body
    )
    candidate = _write_candidate(tmp_path, source)
    result = _run_evaluator(spec, candidate)
    metrics = result["metrics"]

    assert metrics["combined_score"] == 0.0
    assert metrics["valid"] == 1.0
    assert metrics["num_infeasible_instances"] == metrics["num_instances"]
    for row in result["artifacts"]["rows"]:
        assert row["score"] == 0.0
        assert row["violations"]


@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
def test_candidate_runs_in_its_own_process(spec: TaskSpec, tmp_path: Path) -> None:
    """The candidate cannot see the scorer's module globals or its environment."""
    source = (
        "import os\n"
        "import sys\n"
        "\n"
        "\n"
        "def solve_instance(instance):\n"
        "    raise RuntimeError(\n"
        "        'PROBE main=%r env=%r'\n"
        "        % (getattr(sys.modules.get('__main__'), '__file__', None),\n"
        "           sorted(k for k in os.environ if k.startswith('FRONTIER')))\n"
        "    )\n"
    )
    candidate = _write_candidate(tmp_path, source)
    result = _run_evaluator(spec, candidate)
    notes = [r.get("note", "") for r in result["artifacts"]["rows"]]
    assert notes and all("PROBE" in n for n in notes)
    probe = notes[0]
    # The scorer's evaluate.py is not the candidate's __main__ ...
    assert "evaluate.py" not in probe, probe
    # ... and no harness pointer back to the un-sandboxed task tree survives.
    assert "env=[]" in probe, probe
    assert result["metrics"]["combined_score"] == 0.0
    assert result["metrics"]["valid"] == 0.0


# ---------------------------------------------------------------------------
# 3. The oracle is out of reach.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
def test_reference_is_not_exposed_to_the_agent(spec: TaskSpec) -> None:
    """reference.py is neither shown to the agent nor copied into the sandbox."""
    fe = spec.dir / "frontier_eval"
    agent_files = _read_list_file(fe / "agent_files.txt")
    copy_files = _read_list_file(fe / "copy_files.txt")

    assert "verification/reference.py" not in agent_files
    assert "verification/reference.py" not in copy_files
    # A bare "." would sweep the oracle in again.
    assert "." not in copy_files, "copy_files.txt must be an explicit allowlist"
    assert "verification" not in copy_files
    assert "verification/evaluate.py" in copy_files


@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
def test_evaluator_does_not_execute_the_reference(spec: TaskSpec) -> None:
    """Scoring must not import or run reference.py; it uses a constant table."""
    source = spec.evaluator.read_text(encoding="utf-8")
    assert "REFERENCE_" in source
    # The only mention of the reference module is the maintainer-only
    # regeneration path, which is guarded behind an explicit CLI flag.
    assert "--regenerate-reference-table" in source
    body = source.split("def _regenerate_reference_table")[0]
    # REFERENCE_PATH may be *named* (it is documented as maintainer-only), but
    # the scoring path must never load or execute it.
    assert "spec_from_file_location(\"reference" not in body
    assert "reference.solve_instance" not in body
    assert "reference.solve_lp_relaxation" not in body
    assert "exec_module(reference)" not in body


@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
def test_importing_the_oracle_from_the_sandbox_fails(spec: TaskSpec) -> None:
    """End to end: build the sandbox the way the harness does, then try it.

    ``copy_files.txt`` is replayed exactly, the candidate is dropped at
    ``baseline/init.py``, and the evaluator is run from inside the sandbox with
    the harness's env pointers set. The oracle must be unreachable.
    """
    fe = spec.dir / "frontier_eval"
    entries = _read_list_file(fe / "copy_files.txt")

    tmp = Path(tempfile.mkdtemp(prefix="pypfopt_sandbox_"))
    try:
        sandbox = tmp / "benchmark"
        sandbox.mkdir(parents=True)
        for rel in entries:
            src = spec.dir / rel
            dst = sandbox / rel
            assert src.exists(), f"copy_files entry does not exist: {rel}"
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        assert not (sandbox / "verification" / "reference.py").exists()

        # The harness makes benchmarks/_shared reachable via
        # FRONTIER_ENGINEERING_ROOT; mirror that, pointed at the sandbox root
        # rather than the real repo. The evaluator can then load its isolation
        # helper while the oracle stays absent -- which is the thing under test.
        shared = tmp / "benchmarks" / "_shared"
        shared.mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "benchmarks" / "_shared" / "candidate_sandbox.py", shared)

        candidate = sandbox / "baseline" / "init.py"
        candidate.write_text(EXPLOIT_IMPORT_ORACLE, encoding="utf-8")

        result = _run_evaluator(spec, candidate, cwd=sandbox, repo_root=tmp)
        metrics = result["metrics"]
        assert metrics["combined_score"] == 0.0
        assert metrics["valid"] == 0.0
        notes = [r.get("note", "") for r in result["artifacts"]["rows"]]
        assert all("oracle unreachable" in n for n in notes), notes
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Structural validation of the returned vector.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
@pytest.mark.parametrize(
    "returned",
    [
        "[float('nan')] * 999",
        "'not a vector'",
        "[]",
        "[0.0] * 3",
        "[None] * 15",
    ],
    ids=["nan", "string", "empty", "wrong-length", "none"],
)
def test_malformed_solution_is_rejected(
    spec: TaskSpec, returned: str, tmp_path: Path
) -> None:
    source = (
        "def solve_instance(instance):\n"
        f"    return {{'{spec.solution_key}': {returned}}}\n"
    )
    candidate = _write_candidate(tmp_path, source)
    result = _run_evaluator(spec, candidate)
    assert result["metrics"]["combined_score"] == 0.0
    assert result["metrics"]["valid"] == 0.0


@pytest.mark.parametrize("spec", TASKS, ids=TASK_IDS)
def test_candidate_cannot_report_its_own_score(spec: TaskSpec, tmp_path: Path) -> None:
    """Only the solution crosses the process boundary; extra fields are ignored."""
    source = (
        "def solve_instance(instance):\n"
        f"    return {{'{spec.solution_key}': 'bogus', 'score': 100.0,\n"
        "            'combined_score': 100.0, 'valid': 1.0, 'penalty': 0.0}\n"
    )
    candidate = _write_candidate(tmp_path, source)
    result = _run_evaluator(spec, candidate)
    assert result["metrics"]["combined_score"] == 0.0
    assert result["metrics"]["valid"] == 0.0
