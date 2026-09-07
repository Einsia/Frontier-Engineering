#!/usr/bin/env python3
"""Evaluate a discrete (integer-lot) rebalancing candidate.

Hardening notes (why this file looks the way it does):

1. The candidate runs in its **own process**. It used to be ``exec_module``-ed
   into this interpreter, which put the scorer's module globals inside the
   candidate's reach: a single module-level line

       sys.modules['__main__']._feasibility_penalty = lambda *a: 0.0

   erased *every* financial risk constraint (budget, per-asset bounds, sector
   limits, turnover cap, factor exposure), because the penalty function was the
   only place those constraints were enforced and it was looked up by name at
   scoring time. The candidate now only ever hands back a lot vector as JSON.

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
   candidate could ``import`` it, return its lot vector, and land on exactly
   ``obj_cand == obj_ref`` for a free 100/100 without touching a single file. The
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

SEEDS = tuple(range(2226, 2236))

#: Objective value of the reference integer optimum for each evaluation seed,
#: and the LP-relaxation bound reported alongside it. Produced by
#: `verification/reference.py` (CVXPY/HiGHS) via
#: `python verification/evaluate.py --regenerate-reference-table`.
#: The instance generator below is deterministic, so these are exact constants.
REFERENCE_OBJECTIVE: dict[int, float] = {
    2226: 150257.27747896843,
    2227: 74568.11670827433,
    2228: 227000.39208486,
    2229: 191055.2730942929,
    2230: 175147.0196002401,
    2231: 116117.22126280746,
    2232: 261523.57158096193,
    2233: 71703.64694808515,
    2234: 207190.5486118233,
    2235: 139418.12977045914,
}

REFERENCE_LP_BOUND: dict[int, float] = {
    2226: 150255.57253981195,
    2227: 74564.54495050007,
    2228: 227000.3505710193,
    2229: 191049.8639680924,
    2230: 175146.30588111366,
    2231: 116117.20097441967,
    2232: 261521.24133673185,
    2233: 71703.36955381861,
    2234: 207181.42615764923,
    2235: 139417.4860956353,
}

# ---------------------------------------------------------------------------
# Feasibility tolerances.
#
# Lot counts must be exact integers; budget and turnover are notional amounts
# in currency units, so they get an absolute floor plus a term relative to the
# limit itself. The reference MIP (HiGHS) leaves an exactly zero residual on
# every constraint for all 10 seeds, and float summation over 15 unit
# notionals of order 1e5 accumulates at most ~1e-10, so these are generous for
# arithmetic while leaving no room to buy objective: the smallest meaningful
# trade is one lot, worth >= 15 currency units.
# ---------------------------------------------------------------------------
TOL_INTEGRALITY = 1e-6
TOL_LOT_BOUND = 1e-6
TOL_NOTIONAL_ABS = 1e-6
TOL_NOTIONAL_REL = 1e-9

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
#: once per instance, and writes only lot vectors back out. It lives here in
#: a readonly, fingerprinted file rather than on disk in the task tree so a
#: candidate cannot swap it out.
CANDIDATE_RUNNER_SOURCE = '''"""Isolated runner: ask the candidate for lot counts, return only data."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


def _rehydrate(payload: dict) -> dict:
    inst = {
        "prices": np.asarray(payload["prices"], dtype=float),
        "lot_sizes": np.asarray(payload["lot_sizes"], dtype=int),
        "current_lots": np.asarray(payload["current_lots"], dtype=int),
        "target_weights": np.asarray(payload["target_weights"], dtype=float),
        "portfolio_value": float(payload["portfolio_value"]),
        "fee_rate": float(payload["fee_rate"]),
        "turnover_limit_value": float(payload["turnover_limit_value"]),
        "max_lots": np.asarray(payload["max_lots"], dtype=int),
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
        entry = {"seed": payload["seed"], "lots": None, "error": None}
        try:
            out = solve_instance(_rehydrate(payload))
            if not isinstance(out, dict):
                raise TypeError("solve_instance must return a dict")
            lots = np.asarray(out["lots"], dtype=float).reshape(-1)
            entry["lots"] = [float(x) for x in lots.tolist()]
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
def _generate_instance(seed: int, n_assets: int = 15) -> dict:
    rng = np.random.default_rng(seed)

    prices = rng.uniform(15.0, 450.0, size=n_assets)
    lot_sizes = rng.choice([1, 5, 10, 20], size=n_assets, p=[0.55, 0.2, 0.2, 0.05])
    unit = prices * lot_sizes

    current_lots = rng.integers(0, 25, size=n_assets)
    current_value = float((unit * current_lots).sum())

    portfolio_value = float(current_value * rng.uniform(1.0, 1.15))
    target_weights = rng.dirichlet(np.ones(n_assets) * 1.5)

    max_lots = np.maximum(
        current_lots + 5,
        np.floor((portfolio_value / np.maximum(unit, 1e-12)) * rng.uniform(1.2, 1.8, size=n_assets)),
    ).astype(int)

    turnover_limit_value = float(portfolio_value * rng.uniform(0.2, 0.5))

    return {
        "prices": prices,
        "lot_sizes": lot_sizes.astype(int),
        "current_lots": current_lots.astype(int),
        "target_weights": target_weights,
        "portfolio_value": portfolio_value,
        "fee_rate": float(rng.uniform(0.001, 0.004)),
        "turnover_limit_value": turnover_limit_value,
        "max_lots": max_lots,
    }


def _instance_payload(seed: int, instance: dict) -> dict:
    """JSON-safe view of an instance handed to the candidate's subprocess."""
    return {
        "seed": int(seed),
        "prices": instance["prices"].tolist(),
        "lot_sizes": [int(x) for x in instance["lot_sizes"].tolist()],
        "current_lots": [int(x) for x in instance["current_lots"].tolist()],
        "target_weights": instance["target_weights"].tolist(),
        "portfolio_value": float(instance["portfolio_value"]),
        "fee_rate": float(instance["fee_rate"]),
        "turnover_limit_value": float(instance["turnover_limit_value"]),
        "max_lots": [int(x) for x in instance["max_lots"].tolist()],
    }


def _objective(instance: dict, lots: np.ndarray) -> float:
    prices = instance["prices"]
    lot_sizes = instance["lot_sizes"]
    current_lots = instance["current_lots"]
    target_weights = instance["target_weights"]
    portfolio_value = float(instance["portfolio_value"])
    fee_rate = float(instance["fee_rate"])

    unit = prices * lot_sizes
    target_dollar = target_weights * portfolio_value
    lots = np.asarray(lots, dtype=float)

    hold = unit * lots
    traded = unit * np.abs(lots - current_lots)
    traded_notional = traded.sum()

    return float(np.abs(hold - target_dollar).sum() + fee_rate * traded_notional)


# ---------------------------------------------------------------------------
# Candidate output validation + hard feasibility gate.
# ---------------------------------------------------------------------------
class InvalidLotsError(ValueError):
    """The candidate returned something that is not a usable lot vector."""


def validate_lot_vector(raw: object, n_assets: int) -> np.ndarray:
    """Structural validation, before any constraint is looked at."""
    if not isinstance(raw, list):
        raise InvalidLotsError("lots must be a JSON array")
    if len(raw) != n_assets:
        raise InvalidLotsError(f"lots must have length {n_assets}, got {len(raw)}")
    out = np.empty(n_assets, dtype=float)
    for i, value in enumerate(raw):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidLotsError(f"lots[{i}] must be a number, got {value!r}")
        fvalue = float(value)
        if not math.isfinite(fvalue):
            raise InvalidLotsError(f"lots[{i}] must be finite, got {value!r}")
        out[i] = fvalue
    return out


def constraint_residuals(instance: dict, lots: np.ndarray) -> dict[str, float]:
    """Largest violation of each constraint family.

    Every execution constraint of the task is checked here, independently of
    any scoring helper. A value of 0.0 means the constraint is satisfied.
    """
    prices = instance["prices"]
    lot_sizes = instance["lot_sizes"]
    current_lots = np.asarray(instance["current_lots"], dtype=float)
    portfolio_value = float(instance["portfolio_value"])
    fee_rate = float(instance["fee_rate"])
    turnover_limit = float(instance["turnover_limit_value"])
    max_lots = np.asarray(instance["max_lots"], dtype=float)

    unit = prices * lot_sizes
    traded_notional = float((unit * np.abs(lots - current_lots)).sum())
    spend = float((unit * lots).sum() + fee_rate * traded_notional)

    return {
        "integrality": float(np.abs(lots - np.rint(lots)).max()),
        "lot_lower": float(np.maximum(0.0, -lots).max()),
        "lot_upper": float(np.maximum(0.0, lots - max_lots).max()),
        "turnover_notional": max(0.0, traded_notional - turnover_limit),
        "budget": max(0.0, spend - portfolio_value),
    }


def constraint_tolerances(instance: dict) -> dict[str, float]:
    """Per-instance tolerances. Notional limits scale with the limit itself."""
    turnover_limit = float(instance["turnover_limit_value"])
    portfolio_value = float(instance["portfolio_value"])
    return {
        "integrality": TOL_INTEGRALITY,
        "lot_lower": TOL_LOT_BOUND,
        "lot_upper": TOL_LOT_BOUND,
        "turnover_notional": TOL_NOTIONAL_ABS + TOL_NOTIONAL_REL * abs(turnover_limit),
        "budget": TOL_NOTIONAL_ABS + TOL_NOTIONAL_REL * abs(portfolio_value),
    }


def check_feasibility(instance: dict, lots: np.ndarray) -> tuple[bool, list[str], dict]:
    """Hard gate. Returns (feasible, violation messages, residuals)."""
    residuals = constraint_residuals(instance, lots)
    tolerances = constraint_tolerances(instance)
    violations = [
        f"{name} violated by {residuals[name]:.3e} (tolerance {tol:.1e})"
        for name, tol in tolerances.items()
        if residuals[name] > tol
    ]
    return (not violations), violations, residuals


def _score_instance(instance: dict, lots_cand: np.ndarray | None, obj_ref: float) -> dict:
    current = np.asarray(instance["current_lots"], dtype=float)
    obj_anchor = _objective(instance, current)
    if obj_anchor < obj_ref + 1e-8:
        obj_anchor = obj_ref + 1e-3

    row: dict = {
        "obj_ref": obj_ref,
        "obj_anchor": obj_anchor,
        "obj_cand": None,
        "feasible": False,
        "score": 0.0,
        "violations": [],
        "max_residual": None,
    }

    if lots_cand is None:
        row["violations"] = ["no usable lot vector"]
        return row

    obj_cand = _objective(instance, lots_cand)
    row["obj_cand"] = obj_cand

    feasible, violations, residuals = check_feasibility(instance, lots_cand)
    row["feasible"] = feasible
    row["violations"] = violations
    row["residuals"] = {k: float(v) for k, v in residuals.items()}
    row["max_residual"] = float(max(residuals.values()))

    if not feasible:
        # Hard gate. This is the constraint that mattered most here: a basket
        # that ignores the turnover cap reaches a *lower* objective than the
        # true integer optimum, so under the old soft penalty an infeasible
        # order list was worth up to 100 points.
        row["score"] = 0.0
        return row

    norm = (obj_anchor - obj_cand) / (obj_anchor - obj_ref + 1e-12)
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
        obj_ref = REFERENCE_OBJECTIVE[seed]

        lots_cand = None
        note = error
        if results is not None:
            entry = results[idx] if isinstance(results[idx], dict) else {}
            if entry.get("error"):
                note = str(entry["error"])
            else:
                try:
                    lots_cand = validate_lot_vector(
                        entry.get("lots"), instance["prices"].size
                    )
                except InvalidLotsError as exc:
                    note = str(exc)

        row = _score_instance(instance, lots_cand, obj_ref)
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
        "lp_bounds": [REFERENCE_LP_BOUND[seed] for seed in SEEDS],
        "avg_obj_ref": float(np.mean([REFERENCE_OBJECTIVE[seed] for seed in SEEDS])),
        "avg_obj_lp": float(np.mean([REFERENCE_LP_BOUND[seed] for seed in SEEDS])),
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
    bounds = {}
    for seed in SEEDS:
        instance = _generate_instance(seed)
        lots_ref = np.asarray(reference.solve_instance(instance)["lots"], dtype=float)
        bounds[seed] = float(reference.solve_lp_relaxation(instance)["objective"])
        print(f"    {seed}: {_objective(instance, lots_ref)!r},")
    print("}")
    print()
    print("REFERENCE_LP_BOUND: dict[int, float] = {")
    for seed in SEEDS:
        print(f"    {seed}: {bounds[seed]!r},")
    print("}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate discrete_rebalance_mip candidate."
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

    print("=== Task 03 Evaluation ===")
    if result["candidate_error"]:
        print(f"candidate error: {result['candidate_error']}")
    for r in rows:
        obj_cand = "n/a" if r["obj_cand"] is None else f"{r['obj_cand']:.2f}"
        status = "ok" if r["feasible"] else "INFEASIBLE"
        print(
            f"seed={r['seed']} score={r['score']:.2f} "
            f"obj(base)={obj_cand} obj(ref)={r['obj_ref']:.2f} {status}"
        )
        for violation in r["violations"]:
            print(f"    - {violation}")

    print("---")
    print(f"baseline_average_score: {avg_score:.2f}/100")
    print(f"infeasible_instances: {result['n_infeasible']}/{len(rows)}")
    print("reference_integer_upper_bound_score: 100.00/100")
    print(
        f"average_lp_relaxation_objective_lower_bound: {result['avg_obj_lp']:.2f} "
        f"(reference average objective: {result['avg_obj_ref']:.2f})"
    )

    metrics = {
        "combined_score": avg_score,
        "valid": float(result["valid"]),
        "baseline_average_score_100": avg_score,
        "num_instances": float(len(rows)),
        "num_infeasible_instances": float(result["n_infeasible"]),
        "raw_average_score_100": float(result["raw_avg_score"]),
        "average_lp_relaxation_objective_lower_bound": float(result["avg_obj_lp"]),
        "reference_average_objective": float(result["avg_obj_ref"]),
    }
    artifacts = {
        "candidate_path": str(candidate_path),
        "rows": rows,
        "candidate_error": result["candidate_error"],
        "lp_bounds": result["lp_bounds"],
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
