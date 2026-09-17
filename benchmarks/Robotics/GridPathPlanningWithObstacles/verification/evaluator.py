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
        if (parent / 'benchmarks').is_dir() and (parent / 'frontier_eval').is_dir():
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
    from benchmarks.Robotics.GridPathPlanningWithObstacles.baseline.solution import plan_path as baseline_plan_path
    from benchmarks.Robotics.GridPathPlanningWithObstacles.runtime.problem import GOAL, FREE_GRID, REFERENCE_COST, START, path_cost
except ModuleNotFoundError:
    from baseline.solution import plan_path as baseline_plan_path
    from runtime.problem import GOAL, FREE_GRID, REFERENCE_COST, START, path_cost


def evaluate(program_path: str):
    metrics = {
        'combined_score': -1e18,
        'valid': 0.0,
        'candidate_cost': 0.0,
        'baseline_cost': 0.0,
        'reference_cost': float(REFERENCE_COST),
    }
    artifacts = {}
    namespace = runpy.run_path(str(Path(program_path).expanduser().resolve()), run_name='candidate_program')
    plan_path_fn = namespace.get('plan_path')
    if not callable(plan_path_fn):
        artifacts['error_message'] = 'candidate must define plan_path(grid, start, goal)'
        return metrics, artifacts
    try:
        baseline_cost = float(path_cost(baseline_plan_path(FREE_GRID, START, GOAL)))
        candidate_cost = float(path_cost(plan_path_fn(FREE_GRID, START, GOAL)))
    except Exception:
        artifacts['error_message'] = traceback.format_exc()
        return metrics, artifacts
    if not math.isfinite(candidate_cost) or candidate_cost <= 0:
        artifacts['error_message'] = 'candidate cost is invalid'
        return metrics, artifacts
    metrics['valid'] = 1.0
    metrics['candidate_cost'] = candidate_cost
    metrics['baseline_cost'] = baseline_cost
    metrics['combined_score'] = -candidate_cost
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('program')
    parser.add_argument('--metrics-out', default='metrics.json')
    args = parser.parse_args()
    metrics, artifacts = evaluate(args.program)
    Path(args.metrics_out).write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    if artifacts:
        Path('artifacts.json').write_text(json.dumps(artifacts, indent=2), encoding='utf-8')
    print(json.dumps(metrics, indent=2))


if __name__ == '__main__':
    main()
