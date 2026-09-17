from __future__ import annotations

import argparse
import json
import math
import runpy
import traceback
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    return Path.cwd().resolve()


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_path() -> None:
    import sys

    for p in (_repo_root(), _benchmark_root()):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.StructuralOptimization.CantileverComplianceTopologyOptimization.baseline.solution import update_density as baseline_update_density
    from benchmarks.StructuralOptimization.CantileverComplianceTopologyOptimization.runtime.problem import run_optimization
except ModuleNotFoundError:
    from baseline.solution import update_density as baseline_update_density
    from runtime.problem import run_optimization


def evaluate(program_path: str) -> tuple[dict[str, float], dict[str, str]]:
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_compliance": 0.0,
        "baseline_compliance": 0.0,
        "final_volume_fraction": 0.0,
        "volume_fraction_error": 0.0,
    }
    artifacts: dict[str, str] = {}

    program = Path(program_path).expanduser().resolve()
    namespace = runpy.run_path(str(program), run_name="candidate_program")
    update_density = namespace.get("update_density")
    if not callable(update_density):
        artifacts["error_message"] = "candidate must define update_density(density, sensitivity, state)"
        return metrics, artifacts

    try:
        baseline = run_optimization(baseline_update_density)
        candidate = run_optimization(update_density)
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts

    baseline_compliance = float(baseline["compliance"])
    candidate_compliance = float(candidate["compliance"])
    if not math.isfinite(baseline_compliance) or baseline_compliance <= 0:
        artifacts["error_message"] = "internal baseline produced an invalid compliance value"
        return metrics, artifacts
    if not math.isfinite(candidate_compliance) or candidate_compliance <= 0:
        artifacts["error_message"] = "candidate produced an invalid compliance value"
        return metrics, artifacts

    metrics["valid"] = 1.0
    metrics["candidate_compliance"] = candidate_compliance
    metrics["baseline_compliance"] = baseline_compliance
    metrics["final_volume_fraction"] = float(candidate["final_volume_fraction"])
    metrics["volume_fraction_error"] = float(candidate["volume_fraction_error"])
    metrics["combined_score"] = -candidate_compliance
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    parser.add_argument("--metrics-out", default="metrics.json")
    args = parser.parse_args()
    metrics, artifacts = evaluate(args.program)
    Path(args.metrics_out).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if artifacts:
        Path("artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
