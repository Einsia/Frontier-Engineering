"""Multi-seed statistics for the CVRP baseline.

The released evaluation set (24 instances: 12 public + 12 held-out) is fixed,
so the baseline solver is deterministic on it. To satisfy "multi-seed /
multi-run statistics" (reviewer request), this script derives *fresh*
evaluation instance sets from multiple seeds (via
`generate_instances.generate_instance(..., seed=...)`), computes each set's
reference distances on the fly (deterministic GRASP + LNS), and reports the
baseline score distribution across seeds.

Usage (inside the CVRP task directory):
    python verification/multiseed_stat.py [--seeds 111 222 333]

Deterministic: same command + same machine yields the same numbers.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluator import validate  # noqa: E402
from generate_instances import SPECS, generate_instance  # noqa: E402
from ref_solver import grasp_solve, parse_instance, route_dist  # noqa: E402

CVRP_ROOT = Path(__file__).resolve().parents[1]
BASELINE = CVRP_ROOT / "baseline" / "solver.py"
REF_SEEDS = (123, 2024, 7)  # same fixed seed list as ref_solver.main()


def reference_distance(inst: dict) -> int:
    iters = max(100, 4 * inst["n"])
    return min(
        sum(
            route_dist(r, inst["distance"])
            for r in grasp_solve(inst, starts=40, seed=seed, lns_iters=iters)
        )
        for seed in REF_SEEDS
    )


def run_baseline(
    python: str, inst_path: Path, out_path: Path, timeout: float
) -> list:
    proc = subprocess.run(
        [python, str(BASELINE), str(inst_path), str(out_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(BASELINE.parent),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"baseline failed on {inst_path.name}: {proc.stderr[:200]}")
    return json.loads(out_path.read_text(encoding="utf-8"))


def score_seed(seed: int, python: str, tmp: Path, timeout: float) -> tuple[float, list]:
    """Derive one instance set from `seed`; return (combined, per-instance)."""
    inst_dir = tmp / f"s{seed}"
    inst_dir.mkdir(parents=True, exist_ok=True)
    scores = []
    for i, (name, n, k, v, _seed_key) in enumerate(SPECS):
        fname = f"S{seed}-{i + 1}"
        text = generate_instance(fname, n, k, v, seed=seed * 1000 + i)
        inst_path = inst_dir / f"{fname}.vrp"
        inst_path.write_text(text, encoding="ascii", newline="\n")

        inst = parse_instance(inst_path)
        ref = reference_distance(inst)

        out_path = inst_dir / f"{fname}.out.json"
        routes = run_baseline(python, inst_path, out_path, timeout)
        ok, note, cand = validate(routes, inst)
        if not ok:
            raise RuntimeError(f"baseline invalid on {fname}: {note}")
        scores.append(min(100.0, 100.0 * ref / cand))
    return statistics.fmean(scores), scores


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CVRP baseline multi-seed stats")
    parser.add_argument("--seeds", nargs="*", type=int, default=[111, 222, 333])
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    python = sys.executable
    with tempfile.TemporaryDirectory(prefix="cvrp_multiseed_") as td:
        tmp = Path(td)
        per_seed: list[tuple[int, float, list]] = []
        for seed in args.seeds:
            combined, scores = score_seed(seed, python, tmp, args.timeout)
            per_seed.append((seed, combined, scores))
            print(f"seed {seed}: combined={combined:.2f}")

    combined_values = [c for _, c, _ in per_seed]
    print(
        f"multi-seed: mean={statistics.fmean(combined_values):.2f} "
        f"std={statistics.pstdev(combined_values):.2f} "
        f"min={min(combined_values):.2f} max={max(combined_values):.2f} "
        f"seeds={args.seeds}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
