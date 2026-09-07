#!/usr/bin/env python3
"""Evaluate a robust MVO rebalancing candidate.

Hardening notes (why this file looks the way it does):

1. The candidate runs in its **own process**. It used to be ``exec_module``-ed
   into this interpreter, which put the scorer's module globals inside the
   candidate's reach: a single module-level line

       sys.modules['__main__']._feasibility_penalty = lambda *a: 0.0

   erased *every* financial risk constraint (budget, per-asset bounds, sector
   limits, turnover cap, factor exposure), because the penalty function was the
   only place those constraints were enforced and it was looked up by name at
   scoring time. The candidate now only ever hands back a weight vector as JSON.

2. Constraints are a **hard feasibility gate**, not a soft multiplier. The old
   score was ``100 * norm * (1 - penalty)``, so a portfolio that breached the
   turnover cap or a sector limit merely lost a slice of its score -- a
   solution that is not deployable was still worth points, and breaching a
   limit by a hair was a legal way to buy objective. Now any residual above the
   documented tolerance sets the instance score to 0 and marks the run invalid.
   Constraint enforcement no longer lives in a single monkeypatchable hook.

3. The reference optimum is a **precomputed constant table**, not a module that
   gets imported and executed at scoring time. ``verification/reference.py``
   used to be listed in ``agent_files.txt`` and copied into the sandbox, so a
   candidate could ``import`` it, return its weights, and land on exactly
   ``f_cand == f_ref`` for a free 100/100 without touching a single file. The
   seeds are fixed, so the reference objective is fully precomputable; the
   reference module is no longer shipped to the candidate or executed here.
   Regenerate the table with ``--regenerate-reference-table`` (maintainer only).
"""

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

SEEDS = tuple(range(2026, 2036))

#: Objective value of the reference convex optimum for each evaluation seed.
#: Produced by `verification/reference.py` (CVXPY/SCS) via
#: `python verification/evaluate.py --regenerate-reference-table`.
#: The instance generator below is deterministic, so these are exact constants.
REFERENCE_OBJECTIVE: dict[int, float] = {
    2026: 0.06578225748394709,
    2027: 0.05387060675444052,
    2028: 0.07023805688257476,
    2029: 0.07579721839632456,
    2030: -0.00751279774892402,
    2031: 0.017262978907597842,
    2032: 0.06903964950244182,
    2033: 0.03289711522880038,
    2034: 0.045857340932911946,
    2035: 0.04053447046336589,
}

# ---------------------------------------------------------------------------
# Feasibility tolerances.
#
# These are absolute residuals in portfolio-weight units (fractions of NAV).
# They are set roughly an order of magnitude above the worst residual a
# reference-grade convex solver leaves at default settings on these instances,
# measured over all 10 seeds:
#
#   budget |sum(w)-1|        observed <= 5.5e-10   tolerance 1e-6
#   per-asset bounds         observed <= 7.4e-10   tolerance 1e-6
#   sector bounds            observed <= 1.9e-07   tolerance 1e-5
#   factor exposure          observed <= 1.7e-07   tolerance 1e-5
#   turnover ||w-w_prev||_1  observed <= 5.4e-06   tolerance 1e-4
#
# The aggregate constraints get more room because first-order solvers leak
# proportionally to the number of terms summed (50 assets here). Even the
# loosest of these is ~3 orders of magnitude below any breach that could buy a
# measurable amount of objective: at the 1e-4 turnover tolerance the extra
# objective available is ~1e-5, against an f_ref - f_anchor spread of 1e-2.
# ---------------------------------------------------------------------------
TOL_BUDGET = 1e-6
TOL_BOUND = 1e-6
TOL_SECTOR = 1e-5
TOL_FACTOR = 1e-5
TOL_TURNOVER = 1e-4

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
        "mu": np.asarray(payload["mu"], dtype=float),
        "cov": np.asarray(payload["cov"], dtype=float),
        "w_prev": np.asarray(payload["w_prev"], dtype=float),
        "lower": np.asarray(payload["lower"], dtype=float),
        "upper": np.asarray(payload["upper"], dtype=float),
        "sector_ids": np.asarray(payload["sector_ids"], dtype=int),
        "sector_lower": {int(k): float(v) for k, v in payload["sector_lower"].items()},
        "sector_upper": {int(k): float(v) for k, v in payload["sector_upper"].items()},
        "factor_loadings": np.asarray(payload["factor_loadings"], dtype=float),
        "factor_lower": np.asarray(payload["factor_lower"], dtype=float),
        "factor_upper": np.asarray(payload["factor_upper"], dtype=float),
        "risk_aversion": float(payload["risk_aversion"]),
        "transaction_penalty": float(payload["transaction_penalty"]),
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
def _make_psd_matrix(rng: np.random.Generator, n: int, f: int = 8) -> np.ndarray:
    B = rng.normal(0, 0.25, size=(n, f))
    D = rng.uniform(0.03, 0.12, size=n)
    cov = B @ B.T + np.diag(D)
    cov = 0.5 * (cov + cov.T)
    return cov


def _generate_instance(
    seed: int, n_assets: int = 50, n_sectors: int = 8, n_factors: int = 4
) -> dict:
    rng = np.random.default_rng(seed)

    mu = rng.normal(0.06, 0.08, size=n_assets)
    cov = _make_psd_matrix(rng, n_assets)

    lower = np.zeros(n_assets)
    upper = rng.uniform(0.03, 0.10, size=n_assets)

    # Construct feasible previous holdings under per-asset bounds.
    # We sample inside [0, upper] then scale to sum to one.
    for _ in range(100):
        raw = rng.uniform(0.0, 1.0, size=n_assets) * upper
        if raw.sum() > 1.0:
            w_prev = raw / raw.sum()
            break
    else:  # pragma: no cover
        w_prev = np.ones(n_assets) / n_assets

    sector_ids = np.array([i % n_sectors for i in range(n_assets)], dtype=int)

    sector_lower = {}
    sector_upper = {}
    for s in range(n_sectors):
        sec = float(w_prev[sector_ids == s].sum())
        width = float(rng.uniform(0.015, 0.04))
        sector_lower[s] = max(0.0, sec - width)
        sector_upper[s] = min(1.0, sec + width)

    factor_loadings = rng.normal(0.0, 1.0, size=(n_assets, n_factors))
    factor_prev = factor_loadings.T @ w_prev
    factor_width = rng.uniform(0.02, 0.06, size=n_factors)
    factor_lower = factor_prev - factor_width
    factor_upper = factor_prev + factor_width

    instance = {
        "mu": mu,
        "cov": cov,
        "w_prev": w_prev,
        "lower": lower,
        "upper": upper,
        "sector_ids": sector_ids,
        "sector_lower": sector_lower,
        "sector_upper": sector_upper,
        "factor_loadings": factor_loadings,
        "factor_lower": factor_lower,
        "factor_upper": factor_upper,
        "risk_aversion": float(rng.uniform(3.0, 7.0)),
        "transaction_penalty": float(rng.uniform(0.01, 0.04)),
        "turnover_limit": float(rng.uniform(0.15, 0.30)),
    }
    return instance


def _instance_payload(seed: int, instance: dict) -> dict:
    """JSON-safe view of an instance handed to the candidate's subprocess."""
    return {
        "seed": int(seed),
        "mu": instance["mu"].tolist(),
        "cov": instance["cov"].tolist(),
        "w_prev": instance["w_prev"].tolist(),
        "lower": instance["lower"].tolist(),
        "upper": instance["upper"].tolist(),
        "sector_ids": [int(x) for x in instance["sector_ids"].tolist()],
        "sector_lower": {str(int(k)): float(v) for k, v in instance["sector_lower"].items()},
        "sector_upper": {str(int(k)): float(v) for k, v in instance["sector_upper"].items()},
        "factor_loadings": instance["factor_loadings"].tolist(),
        "factor_lower": instance["factor_lower"].tolist(),
        "factor_upper": instance["factor_upper"].tolist(),
        "risk_aversion": float(instance["risk_aversion"]),
        "transaction_penalty": float(instance["transaction_penalty"]),
        "turnover_limit": float(instance["turnover_limit"]),
    }


def _objective(instance: dict, w: np.ndarray) -> float:
    mu = instance["mu"]
    cov = instance["cov"]
    w_prev = instance["w_prev"]
    ra = instance["risk_aversion"]
    tc = instance["transaction_penalty"]
    return float(mu @ w - ra * (w @ cov @ w) - tc * np.abs(w - w_prev).sum())


# ---------------------------------------------------------------------------
# Candidate output validation + hard feasibility gate.
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
    lower = instance["lower"]
    upper = instance["upper"]
    sector_ids = instance["sector_ids"]
    sector_lower = instance["sector_lower"]
    sector_upper = instance["sector_upper"]
    factor_loadings = instance["factor_loadings"]
    factor_lower = instance["factor_lower"]
    factor_upper = instance["factor_upper"]
    w_prev = instance["w_prev"]
    turnover_limit = instance["turnover_limit"]

    sector_res = 0.0
    for s, lo in sector_lower.items():
        sec = float(w[sector_ids == int(s)].sum())
        sector_res = max(sector_res, float(lo) - sec)
    for s, hi in sector_upper.items():
        sec = float(w[sector_ids == int(s)].sum())
        sector_res = max(sector_res, sec - float(hi))

    exposure = factor_loadings.T @ w
    factor_res = max(
        float(np.maximum(0.0, factor_lower - exposure).max()),
        float(np.maximum(0.0, exposure - factor_upper).max()),
    )

    return {
        "budget": abs(float(w.sum()) - 1.0),
        "lower_bound": float(np.maximum(0.0, lower - w).max()),
        "upper_bound": float(np.maximum(0.0, w - upper).max()),
        "sector": max(0.0, sector_res),
        "turnover": max(0.0, float(np.abs(w - w_prev).sum()) - turnover_limit),
        "factor": max(0.0, factor_res),
    }


CONSTRAINT_TOLERANCES = {
    "budget": TOL_BUDGET,
    "lower_bound": TOL_BOUND,
    "upper_bound": TOL_BOUND,
    "sector": TOL_SECTOR,
    "turnover": TOL_TURNOVER,
    "factor": TOL_FACTOR,
}


def check_feasibility(instance: dict, w: np.ndarray) -> tuple[bool, list[str], dict]:
    """Hard gate. Returns (feasible, violation messages, residuals)."""
    residuals = constraint_residuals(instance, w)
    violations = [
        f"{name} violated by {residuals[name]:.3e} (tolerance {tol:.1e})"
        for name, tol in CONSTRAINT_TOLERANCES.items()
        if residuals[name] > tol
    ]
    return (not violations), violations, residuals


def _score_instance(instance: dict, w_cand: np.ndarray | None, f_ref: float) -> dict:
    n = instance["mu"].size
    w_uni = np.ones(n) / n

    f_prev = _objective(instance, instance["w_prev"])
    f_uni = _objective(instance, w_uni)

    f_anchor = min(f_uni, f_prev)
    if f_anchor >= f_ref - 1e-12:
        f_anchor = f_ref - 1e-3

    row: dict = {
        "f_ref": f_ref,
        "f_anchor": f_anchor,
        "f_cand": None,
        "feasible": False,
        "score": 0.0,
        "violations": [],
        "max_residual": None,
    }

    if w_cand is None:
        row["violations"] = ["no usable weight vector"]
        return row

    f_cand = _objective(instance, w_cand)
    row["f_cand"] = f_cand

    feasible, violations, residuals = check_feasibility(instance, w_cand)
    row["feasible"] = feasible
    row["violations"] = violations
    row["residuals"] = {k: float(v) for k, v in residuals.items()}
    row["max_residual"] = float(max(residuals.values()))

    if not feasible:
        # Hard gate: an infeasible portfolio is not deployable. No partial
        # credit, and in particular no way to buy objective with a small breach.
        row["score"] = 0.0
        return row

    norm = (f_cand - f_anchor) / (f_ref - f_anchor + 1e-12)
    row["norm"] = float(np.clip(norm, 0.0, 1.0))
    row["score"] = 100.0 * row["norm"]
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
        f_ref = REFERENCE_OBJECTIVE[seed]

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

        row = _score_instance(instance, w_cand, f_ref)
        row["seed"] = seed
        if note:
            row["note"] = note
            if not row["violations"]:
                row["violations"] = [note]
        rows.append(row)

    n_infeasible = sum(1 for r in rows if not r["feasible"])
    valid = 1.0 if (error is None and n_infeasible == 0) else 0.0
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
# Maintainer utility: regenerate REFERENCE_OBJECTIVE from reference.py.
# ---------------------------------------------------------------------------
def _regenerate_reference_table() -> None:  # pragma: no cover - maintainer path
    spec = importlib.util.spec_from_file_location("reference_solution", str(REFERENCE_PATH))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {REFERENCE_PATH}")
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)

    print("REFERENCE_OBJECTIVE: dict[int, float] = {")
    for seed in SEEDS:
        instance = _generate_instance(seed)
        w_ref = np.asarray(reference.solve_instance(instance)["weights"], dtype=float)
        print(f"    {seed}: {_objective(instance, w_ref)!r},")
    print("}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate robust_mvo_rebalance candidate."
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

    print("=== Task 01 Evaluation ===")
    if result["candidate_error"]:
        print(f"candidate error: {result['candidate_error']}")
    for r in rows:
        f_cand = "n/a" if r["f_cand"] is None else f"{r['f_cand']:.6f}"
        status = "ok" if r["feasible"] else "INFEASIBLE"
        print(
            f"seed={r['seed']} score={r['score']:.2f} "
            f"obj(base)={f_cand} obj(ref)={r['f_ref']:.6f} {status}"
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
        "constraint_tolerances": CONSTRAINT_TOLERANCES,
    }

    if args.metrics_out:
        _write_json(args.metrics_out, metrics)
    if args.artifacts_out:
        _write_json(args.artifacts_out, artifacts)


if __name__ == "__main__":
    main()
