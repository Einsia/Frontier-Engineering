"""CVRP verification evaluator.

Runs a candidate solver program on a fixed set of CVRP instances (public +
held-out), validates the produced routes (full coverage, no duplicates,
capacity respected) and scores each instance relative to the precomputed
reference distance:

    score = min(100, 100 * reference_distance / candidate_distance)

An invalid/crashing/timing-out candidate scores 0 on that instance and marks
the whole run invalid.

Security / integrity:
  * The candidate is checked before running: the EVOLVE-BLOCK markers must be
    present, code outside the markers must match the initial baseline, and the
    source must not reference the verification module, the reference solver,
    reference.json, absolute filesystem paths, or hardcode per-instance routes.
  * The candidate subprocess runs with an environment stripped of
    FRONTIER_EVAL_UNIFIED_* variables and any reference-distance settings, so
    it cannot learn where the scoring baseline lives.
  * reference.json is read from the host benchmark directory (via
    FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR when running inside the unified
    sandbox) and is NOT copied into the sandbox.

Usage (inside the CVRP task directory):
    python verification/evaluator.py baseline/solver.py
    python verification/evaluator.py baseline/solver.py --instances VRP-19-2 VRP-32-5

Environment overrides:
    CVRP_EVAL_TIMEOUT_S      per-instance subprocess timeout (default 60)
    CVRP_EVAL_INSTANCES      space/comma separated subset of instance names
    CVRP_EVAL_MAX_INSTANCES  cap on number of instances
    CVRP_EVAL_SCORE_SCALE    score knob (default 1.0)
    CVRP_EVAL_REFERENCE_JSON override path to reference.json (testing only)
    CVRP_EVAL_GENERATE_SEED  when set, additionally generate fresh instances
                             from this seed at evaluation time (anti-hardcoding:
                             the candidate cannot have seen them); each generated
                             instance is scored against a reference computed on
                             the fly by the reference solver
    CVRP_EVAL_GENERATE_COUNT number of generated instances (default 6)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

TASK_ROOT = Path(__file__).resolve().parents[1]  # <repo>/benchmarks/VehicleRouting/CVRP
INSTANCES_DIR = TASK_ROOT / "data" / "instances"
HELDOUT_DIR = TASK_ROOT / "data" / "instances_heldout"
REFERENCE_JSON = TASK_ROOT / "data" / "reference.json"
BASELINE_PATH = TASK_ROOT / "baseline" / "solver.py"

# Candidate integrity checks live in validator.py (shared with tests).
from validator import (  # noqa: E402
    EVOLVE_START,
    EVOLVE_END,
    candidate_env,
    check_candidate,
    check_determinism,
    select_determinism_probes,
    split_evolve_blocks,
)

# Runtime instance generation (anti-hardcoding) reuses the deterministic
# instance generator and the reference solver; see the design note in
# investigating/docs/CVRP_heldout_记忆漏洞_问题与修复方案.md.
from generate_instances import SPECS, generate_instance  # noqa: E402
from ref_solver import grasp_solve, route_dist  # noqa: E402

# Same fixed seed list the reference solver uses when producing reference.json.
REF_SEEDS = (123, 2024, 7)
DEFAULT_GENERATE_COUNT = 6

# Backward-compatible alias used by the unit tests.
_split_evolve_blocks = split_evolve_blocks

DEFAULT_TIMEOUT_S = 60


def parse_instance(path: Path) -> dict:
    """Parse a TSPLIB-style CVRP .vrp file into an instance dict."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    coords: dict[int, tuple[float, float]] = {}
    demands: dict[int, int] = {}
    capacity = 0
    section = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("CAPACITY"):
            capacity = int(line.split(":")[-1].strip())
            continue
        if upper == "NODE_COORD_SECTION":
            section = "coords"
            continue
        if upper == "DEMAND_SECTION":
            section = "demand"
            continue
        if upper == "DEPOT_SECTION":
            section = None
            continue
        if upper == "EOF" or upper.startswith(("EDGE_WEIGHT", "DISPLAY_DATA")):
            section = None
            continue
        if upper.startswith(("NAME", "COMMENT", "TYPE", "DIMENSION")):
            continue
        if section == "coords":
            parts = line.split()
            if len(parts) >= 3:
                coords[int(parts[0])] = (float(parts[1]), float(parts[2]))
        elif section == "demand":
            parts = line.split()
            if len(parts) >= 2:
                demands[int(parts[0])] = int(parts[1])
    n_customers = max(coords) - 1  # depot is id 1, customers are ids 2..n+1
    pts = [coords[1]] + [coords[i] for i in range(2, n_customers + 2)]
    dist = [[0] * (n_customers + 1) for _ in range(n_customers + 1)]
    for i in range(n_customers + 1):
        for j in range(n_customers + 1):
            dx = pts[i][0] - pts[j][0]
            dy = pts[i][1] - pts[j][1]
            dist[i][j] = int(round(math.hypot(dx, dy)))
    return {
        "name": path.stem,
        "n": n_customers,
        "capacity": capacity,
        "demand": [0] + [demands.get(i, 0) for i in range(2, n_customers + 2)],
        "distance": dist,
    }


def route_distance(routes: list, dist: list[list[int]]) -> int:
    total = 0
    for seq in routes:
        if not seq:
            continue
        total += dist[0][seq[0]]
        for a, b in zip(seq, seq[1:]):
            total += dist[a][b]
        total += dist[seq[-1]][0]
    return total


def validate(routes: Any, inst: dict) -> tuple[bool, str, int | None]:
    """Return (ok, error_message, total_distance)."""
    n, cap, demand = inst["n"], inst["capacity"], inst["demand"]
    if not isinstance(routes, list):
        return False, "routes is not a list", None
    seen: list[int] = []
    for seq in routes:
        if not isinstance(seq, list):
            return False, "a route is not a list", None
        load = 0
        for c in seq:
            if not isinstance(c, int) or isinstance(c, bool):
                return False, f"route contains non-integer {c!r}", None
            if c < 1 or c > n:
                return False, f"customer id {c} out of range 1..{n}", None
            if c in seen:
                return False, f"customer {c} visited more than once", None
            seen.append(c)
            load += demand[c]
        if load > cap:
            return False, f"route {seq} exceeds capacity {cap} (load {load})", None
    if set(seen) != set(range(1, n + 1)):
        missing = set(range(1, n + 1)) - set(seen)
        return False, f"customers not served: {sorted(missing)}", None
    return True, "", route_distance(routes, inst["distance"])


def run_candidate(
    python: str, solver_path: Path, inst_path: Path, out_path: Path, timeout: float
) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [python, str(solver_path), str(inst_path), str(out_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(solver_path.parent),
            env=candidate_env(),
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except OSError as exc:
        return False, f"os error: {exc}"
    if proc.returncode != 0:
        return False, f"exited with code {proc.returncode}: {(proc.stderr or '')[:200]}"
    return True, ""


def _source_benchmark_dir() -> Path | None:
    """Host benchmark dir exposed by the unified sandbox (if running there)."""
    raw = os.environ.get("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", "").strip()
    if raw:
        path = Path(raw)
        if path.is_dir():
            return path
    return None


def load_reference() -> dict[str, float]:
    """Reference distances, preferring the host copy over the sandbox copy."""
    candidates: list[Path] = []
    src = _source_benchmark_dir()
    if src is not None:
        candidates.append(src / "data" / "reference.json")
    env_path = os.environ.get("CVRP_EVAL_REFERENCE_JSON", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(REFERENCE_JSON)
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return {k: float(v) for k, v in raw.items()}
        except Exception:
            continue
    return {}


def _parse_env_str(name: str) -> str | None:
    raw = __import__("os").environ.get(name, "").strip()
    return raw or None


def _all_instance_paths() -> list[Path]:
    """Public instances come from the sandbox copy; held-out instances stay on
    the host (never copied into the sandbox), so a candidate cannot read them
    during evolution. They are still scored: the candidate receives their path
    at scoring time (host path in process mode, repo-mount path in docker)."""
    paths = sorted(INSTANCES_DIR.glob("*.vrp"))
    src = _source_benchmark_dir()
    heldout_dir = (src / "data" / "instances_heldout") if src is not None else HELDOUT_DIR
    if heldout_dir.is_dir():
        paths += sorted(heldout_dir.glob("*.vrp"))
    return paths


def _reference_distance(inst: dict) -> float:
    """Deterministic reference distance for an instance (GRASP + LNS, fixed seeds)."""
    iters = max(100, 4 * inst["n"])
    return min(
        sum(
            route_dist(r, inst["distance"])
            for r in grasp_solve(inst, starts=40, seed=seed, lns_iters=iters)
        )
        for seed in REF_SEEDS
    )


def _generate_instances(base_seed: int, count: int, out_dir: Path) -> tuple[list[Path], dict[str, float]]:
    """Generate fresh instances from `base_seed`; return (instance files, ref distances).

    Instance sizes follow the public set's SPECS (cycled), and per-instance RNG
    streams are derived as `base_seed * 1000 + i`, matching multiseed_stat.py.
    Deterministic: same seed + same machine yields the same instances and refs.
    """
    paths: list[Path] = []
    refs: dict[str, float] = {}
    spec_count = len(SPECS)
    for i in range(count):
        name, n, k, v, _seed_key = SPECS[i % spec_count]
        fname = f"GEN-{base_seed}-{i + 1}"
        text = generate_instance(fname, n, k, v, seed=base_seed * 1000 + i)
        inst_path = out_dir / f"{fname}.vrp"
        inst_path.write_text(text, encoding="ascii", newline="\n")
        inst = parse_instance(inst_path)
        refs[fname] = float(_reference_distance(inst))
        paths.append(inst_path)
    return paths, refs


def evaluate(program_path: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    solver_path = Path(program_path).resolve()
    if not solver_path.is_file():
        raise FileNotFoundError(f"candidate solver not found: {solver_path}")

    timeout = float(_parse_env_str("CVRP_EVAL_TIMEOUT_S") or DEFAULT_TIMEOUT_S)
    inst_names = _parse_env_str("CVRP_EVAL_INSTANCES")
    max_instances = _parse_env_str("CVRP_EVAL_MAX_INSTANCES")

    inst_paths = _all_instance_paths()
    if inst_names:
        picked = [p for n in inst_names.replace(",", " ").split() for p in inst_paths if p.stem == n]
        if picked:
            inst_paths = picked
    if max_instances:
        inst_paths = inst_paths[: int(max_instances)]

    reference = load_reference()
    python = sys.executable
    tmp_dir = Path(tempfile.mkdtemp(prefix="cvrp_eval_"))

    # Anti-hardcoding: when a generation seed is provided, add fresh instances
    # generated at evaluation time (the candidate cannot have memorized them).
    gen_seed_raw = _parse_env_str("CVRP_EVAL_GENERATE_SEED")
    if gen_seed_raw:
        try:
            gen_count = int(_parse_env_str("CVRP_EVAL_GENERATE_COUNT") or DEFAULT_GENERATE_COUNT)
            gen_count = max(0, gen_count)
        except ValueError:
            gen_count = DEFAULT_GENERATE_COUNT
        if gen_count > 0:
            gen_paths, gen_refs = _generate_instances(int(gen_seed_raw), gen_count, tmp_dir)
            inst_paths = list(inst_paths) + gen_paths
            reference.update(gen_refs)

    # Static integrity checks + determinism (probe small / medium / large
    # instances; each probe runs the candidate twice).
    src_dir = _source_benchmark_dir()
    baseline_path = (
        (src_dir / "baseline" / "solver.py") if src_dir is not None else BASELINE_PATH
    )
    preflight = check_candidate(solver_path, baseline_path=baseline_path)
    if not preflight and inst_paths:
        for probe in select_determinism_probes(inst_paths, parse_instance):
            det_ok, det_note = check_determinism(
                python, solver_path, probe, timeout
            )
            if not det_ok:
                preflight = [
                    f"determinism check failed on {probe.stem}: {det_note}"
                ]
                break

    rows = []
    for inst_path in inst_paths:
        inst = parse_instance(inst_path)
        out_path = tmp_dir / f"{inst['name']}.out.json"
        ok = True
        err = ""
        if preflight:
            ok = False
            err = "preflight: " + "; ".join(preflight)
        else:
            ok, err = run_candidate(python, solver_path, inst_path, out_path, timeout)
        score = 0.0
        cand_dist = None
        valid = False
        note = err if not ok else ""
        if ok:
            try:
                routes = json.loads(out_path.read_text(encoding="utf-8"))
                valid, note, cand_dist = validate(routes, inst)
            except Exception as exc:
                note = f"output parse error: {exc}"
        if valid and cand_dist is not None and cand_dist > 0:
            ref = reference.get(inst["name"])
            if ref is not None and ref > 0:
                # Score scale: experimental knob to tighten the 100-point bar.
                # Default 1.0 => score = min(100, 100*ref/cand). A scale s means
                # a candidate must be s times shorter than the reference to hit
                # 100 (e.g. s=2/3 => needs cand <= ref*2/3).
                scale = float(os.environ.get("CVRP_EVAL_SCORE_SCALE", "1.0"))
                score = min(100.0, scale * 100.0 * ref / cand_dist)
            else:
                score = 0.0
                valid = False
                note = f"no reference distance for {inst['name']}"
        rows.append(
            {
                "name": inst["name"],
                "valid": bool(valid),
                "score": score,
                "candidate_distance": cand_dist,
                "note": note or "",
            }
        )

    all_valid = all(r["valid"] for r in rows)
    combined = (
        statistics.fmean(r["score"] for r in rows) if rows and all_valid else 0.0
    )
    metrics: dict[str, Any] = {
        "combined_score": float(combined),
        "valid": 1.0 if all_valid and rows else 0.0,
        "instances": float(len(rows)),
        "per_instance": {
            r["name"]: {"score": r["score"], "valid": r["valid"], "note": r["note"]}
            for r in rows
        },
    }
    artifacts = {
        "candidate_path": str(solver_path),
        "timeout_s": timeout,
        # NOTE: reference distances are deliberately NOT included here to avoid
        # leaking the scoring baseline to the agent.
        "reference_instance_count": float(len(reference)),
    }
    return {"metrics": metrics, "artifacts": artifacts}


def _print_report(metrics: dict[str, Any]) -> None:
    print(f"combined_score: {metrics['combined_score']:.2f}")
    print(f"valid: {metrics['valid']}")
    for name, info in metrics.get("per_instance", {}).items():
        flag = "OK " if info["valid"] else "BAD"
        note = f"  ({info['note']})" if info.get("note") else ""
        print(f"  {flag} {name}: score={info['score']:.2f}{note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CVRP candidate evaluator")
    parser.add_argument("candidate", help="path to candidate solver.py")
    parser.add_argument("--instances", nargs="*", default=None)
    args = parser.parse_args(argv)

    os_env = __import__("os").environ
    if args.instances:
        os_env["CVRP_EVAL_INSTANCES"] = " ".join(args.instances)

    t0 = time.perf_counter()
    try:
        result = evaluate(args.candidate)
        metrics, artifacts = result["metrics"], result["artifacts"]
        _print_report(metrics)
        print(f"wall time: {time.perf_counter() - t0:.1f}s")
        return 0
    except Exception:
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
