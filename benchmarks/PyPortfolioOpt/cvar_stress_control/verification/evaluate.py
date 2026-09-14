"""Evaluate isolated candidates with scorer-owned objectives and original soft penalties."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE_PATH = ROOT / "baseline" / "init.py"

#: Maintainer-only. Never imported on the scoring path and deliberately not
#: copied into the candidate sandbox (see frontier_eval/copy_files.txt).
REFERENCE_PATH = ROOT / "verification" / "reference.py"

SEEDS = tuple(range(2126, 2136))

#: CVaR of the reference convex optimum for each evaluation seed.
#: Produced by `verification/reference.py` (CVXPY/SCS) via
#: `python verification/evaluate.py --regenerate-reference-table`.
#: The instance generator below is deterministic, so these are exact constants.
REFERENCE_CVAR: dict[int, float] = {
    2126: 0.004295625545123964,
    2127: 0.005691702887602745,
    2128: 0.005230763316744385,
    2129: 0.007205732495784799,
    2130: 0.007724507719973182,
    2131: 0.004842421825907788,
    2132: 0.005155633996160659,
    2133: 0.005658226721807663,
    2134: 0.004441570458863218,
    2135: 0.0038088466999797975,
}

# ---------------------------------------------------------------------------
# Feasibility tolerances.
#
# Absolute residuals in portfolio-weight units (fractions of NAV), except the
# return floor which is scaled to the size of the target itself. Each is set
# roughly an order of magnitude above the worst residual a reference-grade
# convex solver leaves at default settings on these instances, measured over
# all 10 seeds:
#
#   budget |sum(w)-1|        observed <= 3.0e-08   tolerance 1e-6
#   per-asset bounds         observed <= 1.0e-07   tolerance 1e-6
#   sector bounds            observed == 0.0       tolerance 1e-5
#   turnover ||w-w_prev||_1  observed <= 2.2e-05   tolerance 1e-4
#   return floor mu'w        observed <= 4.2e-09   tolerance 1e-8 + 1e-4*target
#
# The return floor gets a relative term because `target_return` is ~5e-4 here,
# so a flat 1e-6 would be a 0.2% shortfall -- material. At 1e-4 * target the
# admissible shortfall is ~5e-8, i.e. 0.01% of the mandated return.
# ---------------------------------------------------------------------------
TOL_BUDGET = 1e-6
TOL_BOUND = 1e-6
TOL_SECTOR = 1e-5
TOL_TURNOVER = 1e-4
TOL_RETURN_ABS = 1e-8
TOL_RETURN_REL = 1e-4

#: Environment handed to the candidate. Deliberately excludes the harness's
#: FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR / FRONTIER_ENGINEERING_ROOT
#: pointers, which would otherwise hand the candidate a path back to the
#: un-sandboxed task tree (and so to verification/reference.py).
CANDIDATE_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TMP",
    "TEMP",
    "PYTHONHASHSEED",
    "VIRTUAL_ENV",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "SYSTEMROOT",
)

DEFAULT_CANDIDATE_TIMEOUT_S = 240.0


def _import_candidate_sandbox() -> ModuleType:
    """Import the shared isolation helper before any candidate code runs.

    ``benchmarks/_shared/`` sits outside every benchmark directory, so a task's
    ``copy_files.txt`` cannot drag it into the sandbox where a candidate could
    rewrite it.
    """
    try:
        import candidate_sandbox  # type: ignore

        return candidate_sandbox
    except ImportError:
        pass

    roots: list[Path] = []
    env_root = str(os.environ.get("FRONTIER_ENGINEERING_ROOT", "")).strip()
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())
    roots.extend(Path(__file__).resolve().parents)

    for root in roots:
        shared = root / "benchmarks" / "_shared"
        if (shared / "candidate_sandbox.py").is_file():
            sys.path.insert(0, str(shared))
            import candidate_sandbox  # type: ignore

            return candidate_sandbox

    raise RuntimeError(
        "benchmarks/_shared/candidate_sandbox.py not found; set "
        "FRONTIER_ENGINEERING_ROOT to the repository root."
    )


sandbox = _import_candidate_sandbox()


#: Scorer-owned program executed inside the candidate's subprocess. It rebuilds
#: the numpy view of each instance (so ``solve_instance`` sees exactly what it
#: saw when this evaluator still exec'd it in-process), calls the candidate
#: once per instance, and writes only weight vectors back out. It lives here in
#: a readonly, fingerprinted file rather than on disk in the task tree so a
#: candidate cannot swap it out.
CANDIDATE_RUNNER_SOURCE = '''"""Isolated runner: ask the candidate for weights, return only data."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


def _rehydrate(payload: dict) -> dict:
    inst = {
        "scenario_returns": np.asarray(payload["scenario_returns"], dtype=float),
        "mu": np.asarray(payload["mu"], dtype=float),
        "w_prev": np.asarray(payload["w_prev"], dtype=float),
        "lower": np.asarray(payload["lower"], dtype=float),
        "upper": np.asarray(payload["upper"], dtype=float),
        "sector_ids": np.asarray(payload["sector_ids"], dtype=int),
        "sector_lower": {int(k): float(v) for k, v in payload["sector_lower"].items()},
        "sector_upper": {int(k): float(v) for k, v in payload["sector_upper"].items()},
        "beta": float(payload["beta"]),
        "target_return": float(payload["target_return"]),
        "turnover_limit": float(payload["turnover_limit"]),
    }
    return inst


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: runner.py <candidate.py> <instances.json> <submission.json>", file=sys.stderr)
        return 2

    candidate_path = Path(sys.argv[1]).resolve()
    instances_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])

    payloads = json.loads(instances_path.read_text(encoding="utf-8"))

    spec = importlib.util.spec_from_file_location("pypfopt_candidate", candidate_path)
    if spec is None or spec.loader is None:
        print("cannot import candidate module from %s" % candidate_path, file=sys.stderr)
        return 3
    module = importlib.util.module_from_spec(spec)
    sys.modules["pypfopt_candidate"] = module
    spec.loader.exec_module(module)

    solve_instance = getattr(module, "solve_instance", None)
    if not callable(solve_instance):
        print("candidate must define solve_instance(instance) -> dict", file=sys.stderr)
        return 4

    results = []
    for payload in payloads:
        entry = {"seed": payload["seed"], "weights": None, "error": None}
        try:
            out = solve_instance(_rehydrate(payload))
            if not isinstance(out, dict):
                raise TypeError("solve_instance must return a dict")
            weights = np.asarray(out["weights"], dtype=float).reshape(-1)
            entry["weights"] = [float(x) for x in weights.tolist()]
        except Exception as exc:  # candidate failure on one instance
            entry["error"] = "%s: %s" % (type(exc).__name__, exc)
        results.append(entry)

    output_path.write_text(json.dumps({"results": results}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


# ---------------------------------------------------------------------------
# Instance generation (unchanged; deterministic given the seed).
# ---------------------------------------------------------------------------
def _generate_instance(seed: int, n_assets: int = 26, n_sectors: int = 5, T: int = 260) -> dict:
    rng = np.random.default_rng(seed)

    # Heavy-tailed factor model scenarios
    f = 4
    factor = rng.standard_t(df=4, size=(T, f)) * 0.01
    loadings = rng.normal(0.0, 0.7, size=(n_assets, f))
    idio = rng.standard_t(df=5, size=(T, n_assets)) * 0.012
    drift = rng.normal(0.0004, 0.00025, size=n_assets)

    R = factor @ loadings.T + idio + drift
    mu = R.mean(axis=0)

    lower = np.zeros(n_assets)
    upper = rng.uniform(0.07, 0.18, size=n_assets)

    w_prev = rng.dirichlet(np.ones(n_assets) * 2.0)

    sector_ids = np.array([i % n_sectors for i in range(n_assets)], dtype=int)
    sector_lower = {}
    sector_upper = {}

    base = 1.0 / n_sectors
    for s in range(n_sectors):
        lo = max(0.0, base * 0.2 + rng.uniform(-0.015, 0.015))
        hi = min(1.0, base * 2.3 + rng.uniform(-0.04, 0.04))
        sector_lower[s] = float(lo)
        sector_upper[s] = float(max(hi, lo + 0.05))

    sector_upper[int(rng.integers(0, n_sectors))] = min(
        1.0, sector_upper[int(rng.integers(0, n_sectors))] + 0.2
    )

    target_return = float(mu.mean() + 0.05 * mu.std())

    return {
        "scenario_returns": R,
        "mu": mu,
        "w_prev": w_prev,
        "lower": lower,
        "upper": upper,
        "sector_ids": sector_ids,
        "sector_lower": sector_lower,
        "sector_upper": sector_upper,
        "beta": float(rng.uniform(0.9, 0.98)),
        "target_return": target_return,
        "turnover_limit": float(rng.uniform(0.25, 0.55)),
    }


def _instance_payload(seed: int, instance: dict) -> dict:
    """JSON-safe view of an instance handed to the candidate's subprocess."""
    return {
        "seed": int(seed),
        "scenario_returns": instance["scenario_returns"].tolist(),
        "mu": instance["mu"].tolist(),
        "w_prev": instance["w_prev"].tolist(),
        "lower": instance["lower"].tolist(),
        "upper": instance["upper"].tolist(),
        "sector_ids": [int(x) for x in instance["sector_ids"].tolist()],
        "sector_lower": {str(int(k)): float(v) for k, v in instance["sector_lower"].items()},
        "sector_upper": {str(int(k)): float(v) for k, v in instance["sector_upper"].items()},
        "beta": float(instance["beta"]),
        "target_return": float(instance["target_return"]),
        "turnover_limit": float(instance["turnover_limit"]),
    }


def _cvar(R: np.ndarray, w: np.ndarray, beta: float) -> float:
    losses = -(R @ w)
    q = np.quantile(losses, beta)
    tail = losses[losses >= q]
    if tail.size == 0:
        return float(q)
    return float(tail.mean())


# ---------------------------------------------------------------------------
# Candidate output validation and constraint diagnostics.
# ---------------------------------------------------------------------------
class InvalidWeightsError(ValueError):
    """The candidate returned something that is not a usable weight vector."""


def validate_weight_vector(raw: object, n_assets: int) -> np.ndarray:
    """Structural validation, before any constraint is looked at."""
    if not isinstance(raw, list):
        raise InvalidWeightsError("weights must be a JSON array")
    if len(raw) != n_assets:
        raise InvalidWeightsError(
            f"weights must have length {n_assets}, got {len(raw)}"
        )
    out = np.empty(n_assets, dtype=float)
    for i, value in enumerate(raw):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidWeightsError(f"weights[{i}] must be a number, got {value!r}")
        fvalue = float(value)
        if not math.isfinite(fvalue):
            raise InvalidWeightsError(f"weights[{i}] must be finite, got {value!r}")
        out[i] = fvalue
    return out


def constraint_residuals(instance: dict, w: np.ndarray) -> dict[str, float]:
    """Largest violation of each constraint family, in weight units.

    Every financial risk constraint of the task is checked here, independently
    of any scoring helper. A value of 0.0 means the constraint is satisfied.
    """
    mu = instance["mu"]
    lower = instance["lower"]
    upper = instance["upper"]
    sector_ids = instance["sector_ids"]
    sector_lower = instance["sector_lower"]
    sector_upper = instance["sector_upper"]
    target_return = float(instance["target_return"])
    w_prev = instance["w_prev"]
    turnover_limit = float(instance["turnover_limit"])

    sector_res = 0.0
    for s, lo in sector_lower.items():
        sec = float(w[sector_ids == int(s)].sum())
        sector_res = max(sector_res, float(lo) - sec)
    for s, hi in sector_upper.items():
        sec = float(w[sector_ids == int(s)].sum())
        sector_res = max(sector_res, sec - float(hi))

    return {
        "budget": abs(float(w.sum()) - 1.0),
        "lower_bound": float(np.maximum(0.0, lower - w).max()),
        "upper_bound": float(np.maximum(0.0, w - upper).max()),
        "sector": max(0.0, sector_res),
        "turnover": max(0.0, float(np.abs(w - w_prev).sum()) - turnover_limit),
        "target_return": max(0.0, target_return - float(mu @ w)),
    }


def constraint_tolerances(instance: dict) -> dict[str, float]:
    """Per-instance tolerances. The return floor scales with the target."""
    return {
        "budget": TOL_BUDGET,
        "lower_bound": TOL_BOUND,
        "upper_bound": TOL_BOUND,
        "sector": TOL_SECTOR,
        "turnover": TOL_TURNOVER,
        "target_return": TOL_RETURN_ABS
        + TOL_RETURN_REL * abs(float(instance["target_return"])),
    }


def check_feasibility(instance: dict, w: np.ndarray) -> tuple[bool, list[str], dict]:
    """Return constraint diagnostics; the original soft penalty determines the score."""
    residuals = constraint_residuals(instance, w)
    tolerances = constraint_tolerances(instance)
    violations = [
        f"{name} violated by {residuals[name]:.3e} (tolerance {tol:.1e})"
        for name, tol in tolerances.items()
        if residuals[name] > tol
    ]
    return (not violations), violations, residuals


def _feasibility_penalty(instance: dict, w: np.ndarray) -> float:
    mu = instance["mu"]
    lower = instance["lower"]
    upper = instance["upper"]
    sector_ids = instance["sector_ids"]
    sector_lower = instance["sector_lower"]
    sector_upper = instance["sector_upper"]
    target_return = instance["target_return"]
    w_prev = instance["w_prev"]
    turnover_limit = instance["turnover_limit"]

    p = 0.0
    p += max(0.0, abs(w.sum() - 1.0) - 1e-4) * 2.0
    p += np.maximum(0.0, lower - w).sum() * 15.0
    p += np.maximum(0.0, w - upper).sum() * 15.0

    ret = float(mu @ w)
    p += max(0.0, target_return - ret) * 600.0

    for s, lo in sector_lower.items():
        sec = w[sector_ids == int(s)].sum()
        p += max(0.0, lo - sec) * 10.0

    for s, hi in sector_upper.items():
        sec = w[sector_ids == int(s)].sum()
        p += max(0.0, sec - hi) * 10.0

    turn = np.abs(w - w_prev).sum()
    p += max(0.0, turn - turnover_limit) * 10.0

    return float(min(1.0, p))


def _score_instance(instance: dict, w_cand: np.ndarray | None, c_ref: float) -> dict:
    R = instance["scenario_returns"]
    beta = float(instance["beta"])
    w_prev = instance["w_prev"]
    n = instance["mu"].size
    w_uniform = np.ones(n) / n

    c_anchor = max(_cvar(R, w_uniform, beta), _cvar(R, w_prev, beta))
    if c_anchor < c_ref + 1e-6:
        c_anchor = c_ref + 1e-3

    row: dict = {
        "c_ref": c_ref,
        "c_anchor": c_anchor,
        "c_cand": None,
        "feasible": False,
        "score": 0.0,
        "violations": [],
        "max_residual": None,
    }

    if w_cand is None:
        row["violations"] = ["no usable weight vector"]
        return row

    c_cand = _cvar(R, w_cand, beta)
    row["c_cand"] = c_cand

    feasible, violations, residuals = check_feasibility(instance, w_cand)
    row["feasible"] = feasible
    row["violations"] = violations
    row["residuals"] = {k: float(v) for k, v in residuals.items()}
    row["max_residual"] = float(max(residuals.values()))

    norm = (c_anchor - c_cand) / (c_anchor - c_ref + 1e-12)
    row["norm"] = float(np.clip(norm, 0.0, 1.0))
    row["penalty"] = _feasibility_penalty(instance, w_cand)
    row["score"] = 100.0 * row["norm"] * (1.0 - row["penalty"])
    return row


# ---------------------------------------------------------------------------
# Candidate execution.
# ---------------------------------------------------------------------------
def _candidate_timeout_s() -> float:
    raw = str(os.environ.get("PYPFOPT_CANDIDATE_TIMEOUT_S", "")).strip()
    if not raw:
        return DEFAULT_CANDIDATE_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_CANDIDATE_TIMEOUT_S
    return value if value > 0 else DEFAULT_CANDIDATE_TIMEOUT_S


def run_candidate(
    candidate_path: Path, payloads: list[dict], *, timeout_s: float | None = None
) -> tuple[list[dict] | None, str | None]:
    """Run the candidate once, in its own process, over every instance."""
    timeout_s = _candidate_timeout_s() if timeout_s is None else timeout_s
    runner_dir = Path(tempfile.mkdtemp(prefix="pypfopt_runner_"))
    try:
        runner_path = runner_dir / "candidate_runner.py"
        runner_path.write_text(CANDIDATE_RUNNER_SOURCE, encoding="utf-8")

        try:
            run = sandbox.run_candidate_isolated(
                runner_path,
                inputs={"instances.json": json.dumps(payloads).encode("utf-8")},
                expected_outputs=("submission.json",),
                timeout_s=timeout_s,
                argv=[str(Path(candidate_path).resolve()), "instances.json", "submission.json"],
                copy_into_workdir=True,
                env_allowlist=CANDIDATE_ENV_ALLOWLIST,
            )
        except sandbox.InvalidSubmissionError as exc:
            return None, str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            return None, f"failed to run candidate: {exc}"

        if run.timed_out:
            return None, f"candidate timed out after {timeout_s:g}s"
        if run.returncode != 0:
            detail = (run.stderr_tail or run.stdout_tail or "").strip().splitlines()
            tail = detail[-1] if detail else "no output"
            return None, f"candidate exited non-zero ({run.returncode}): {tail[:400]}"

        try:
            submission = sandbox.load_json_output(run)
        except sandbox.InvalidSubmissionError as exc:
            return None, str(exc)
    finally:
        import shutil

        shutil.rmtree(runner_dir, ignore_errors=True)

    results = submission.get("results")
    if not isinstance(results, list) or len(results) != len(payloads):
        return None, "submission.json must contain one result per instance"
    return results, None


def _evaluate_candidate(candidate_path: Path) -> dict:
    instances = {seed: _generate_instance(seed) for seed in SEEDS}
    payloads = [_instance_payload(seed, instances[seed]) for seed in SEEDS]

    results, error = run_candidate(candidate_path, payloads)

    rows = []
    for idx, seed in enumerate(SEEDS):
        instance = instances[seed]
        c_ref = REFERENCE_CVAR[seed]

        w_cand = None
        note = error
        if results is not None:
            entry = results[idx] if isinstance(results[idx], dict) else {}
            if entry.get("error"):
                note = str(entry["error"])
            else:
                try:
                    w_cand = validate_weight_vector(
                        entry.get("weights"), instance["mu"].size
                    )
                except InvalidWeightsError as exc:
                    note = str(exc)

        row = _score_instance(instance, w_cand, c_ref)
        row["seed"] = seed
        if note:
            row["note"] = note
            if not row["violations"]:
                row["violations"] = [note]
        rows.append(row)

    n_infeasible = sum(1 for r in rows if not r["feasible"])
    valid = 1.0 if (error is None and all(r["max_residual"] is not None for r in rows)) else 0.0
    avg_score = float(np.mean([r["score"] for r in rows]))

    return {
        "rows": rows,
        "avg_score": avg_score if valid > 0 else 0.0,
        "raw_avg_score": avg_score,
        "valid": valid,
        "n_infeasible": n_infeasible,
        "candidate_error": error,
    }


# ---------------------------------------------------------------------------
# Maintainer utility: regenerate REFERENCE_CVAR from reference.py.
# ---------------------------------------------------------------------------
def _regenerate_reference_table() -> None:  # pragma: no cover - maintainer path
    spec = importlib.util.spec_from_file_location("reference_solution", str(REFERENCE_PATH))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {REFERENCE_PATH}")
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)

    print("REFERENCE_CVAR: dict[int, float] = {")
    for seed in SEEDS:
        instance = _generate_instance(seed)
        w_ref = np.asarray(reference.solve_instance(instance)["weights"], dtype=float)
        cvar = _cvar(instance["scenario_returns"], w_ref, float(instance["beta"]))
        print(f"    {seed}: {cvar!r},")
    print("}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate cvar_stress_control candidate."
    )
    parser.add_argument(
        "candidate",
        nargs="?",
        default=str(DEFAULT_CANDIDATE_PATH),
        help="Path to candidate Python file.",
    )
    parser.add_argument(
        "--metrics-out",
        type=str,
        default=None,
        help="Optional JSON path for frontier_eval metrics output.",
    )
    parser.add_argument(
        "--artifacts-out",
        type=str,
        default=None,
        help="Optional JSON path for additional artifacts output.",
    )
    parser.add_argument(
        "--regenerate-reference-table",
        action="store_true",
        help="Maintainer only: re-solve the reference and print the constant table.",
    )
    return parser.parse_args()


def _write_json(path: str, payload: dict) -> None:
    out_path = Path(path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = _parse_args()
    if args.regenerate_reference_table:  # pragma: no cover - maintainer path
        _regenerate_reference_table()
        return

    candidate_path = Path(args.candidate).expanduser().resolve()
    result = _evaluate_candidate(candidate_path)
    rows = result["rows"]
    avg_score = float(result["avg_score"])

    print("=== Task 02 Evaluation ===")
    if result["candidate_error"]:
        print(f"candidate error: {result['candidate_error']}")
    for r in rows:
        c_cand = "n/a" if r["c_cand"] is None else f"{r['c_cand']:.6f}"
        status = "ok" if r["feasible"] else "INFEASIBLE"
        print(
            f"seed={r['seed']} score={r['score']:.2f} "
            f"cvar(base)={c_cand} cvar(ref)={r['c_ref']:.6f} {status}"
        )
        for violation in r["violations"]:
            print(f"    - {violation}")

    print("---")
    print(f"baseline_average_score: {avg_score:.2f}/100")
    print(f"infeasible_instances: {result['n_infeasible']}/{len(rows)}")
    print("reference_theoretical_upper_bound: 100.00/100")

    metrics = {
        "combined_score": avg_score,
        "valid": float(result["valid"]),
        "baseline_average_score_100": avg_score,
        "num_instances": float(len(rows)),
        "num_infeasible_instances": float(result["n_infeasible"]),
        "raw_average_score_100": float(result["raw_avg_score"]),
    }
    artifacts = {
        "candidate_path": str(candidate_path),
        "rows": rows,
        "candidate_error": result["candidate_error"],
        "constraint_tolerances": {
            str(seed): constraint_tolerances(_generate_instance(seed))
            for seed in SEEDS
        },
    }

    if args.metrics_out:
        _write_json(args.metrics_out, metrics)
    if args.artifacts_out:
        _write_json(args.artifacts_out, artifacts)


if __name__ == "__main__":
    main()
