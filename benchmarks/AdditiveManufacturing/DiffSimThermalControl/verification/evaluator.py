"""Evaluator for the AdditiveManufacturing/DiffSimThermalControl benchmark.

Isolation contract
------------------
The candidate used to be ``exec_module``-d straight into this process, which put
the scorer, the canonical simulator and the candidate's arbitrary module-level
code in one namespace. A candidate could therefore rebind
``canonical.simulate``/``project_params``, tamper with the ``simulate_fn``
closure cell that counts its budget, or mutate the loaded case list.

Now:

* everything this file needs is imported *before* the candidate ever runs;
* the candidate runs in a throw-away subprocess driven by the trusted
  ``verification/candidate_runner.py`` and returns only data
  (control knots + a call count) via ``submission.json``;
* the scorer validates that data and recomputes *every* scored quantity --
  loss, feasibility, temperatures -- with its own pristine ``canonical``
  module. Nothing the candidate reports is adopted as a score.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

BENCHMARK_DIR = Path(__file__).resolve().parents[1]
VERIFICATION_DIR = Path(__file__).resolve().parent
CANONICAL_PROGRAM = VERIFICATION_DIR / 'canonical.py'
CANDIDATE_RUNNER = VERIFICATION_DIR / 'candidate_runner.py'

# Wall-clock ceiling for the whole candidate run (all cases together).
CANDIDATE_TIMEOUT_S = 900.0


def _find_repo_root() -> Path:
    env_root = (os.environ.get('FRONTIER_ENGINEERING_ROOT') or '').strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / 'benchmarks').is_dir() and (parent / 'frontier_eval').is_dir():
            return parent
    raise RuntimeError('could not locate repo root for DiffSimThermalControl evaluator')


_SHARED_DIR = _find_repo_root() / 'benchmarks' / '_shared'
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
import candidate_sandbox as sandbox  # noqa: E402


def _load_module(name: str, path: Path):
    """Load a *trusted* module (the canonical simulator) by absolute path."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f'failed to load module from {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Imported once, at module import time, i.e. strictly before any candidate runs.
CANONICAL = _load_module('am_canonical', CANONICAL_PROGRAM)


class CandidateRejected(Exception):
    """The candidate ran but produced something the scorer will not score."""


def _canonical_baseline(case: dict[str, Any], max_sim_calls: int) -> dict[str, Any]:
    return CANONICAL.baseline_solve(case, max_sim_calls=max_sim_calls, simulate_fn=CANONICAL.simulate)


def _validate_params(raw: Any, case: dict[str, Any]) -> list[float]:
    """Scorer-owned checks on one case's control knots."""
    if not isinstance(raw, list):
        raise CandidateRejected(f"case {case['case_id']}: 'params' must be a JSON list")
    expected = int(case['control_knots'])
    if len(raw) != expected:
        raise CandidateRejected(
            f"case {case['case_id']}: expected {expected} params, got {len(raw)}"
        )
    params: list[float] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CandidateRejected(
                f"case {case['case_id']}: params entries must be numbers, got {value!r}"
            )
        value = float(value)
        if not math.isfinite(value):
            raise CandidateRejected(f"case {case['case_id']}: all params must be finite")
        params.append(value)
    return params


def _run_candidate(candidate_path: Path, cases: list[dict[str, Any]], max_sim_calls: int) -> dict[str, list[float]]:
    """Run the candidate out-of-process and return validated knots per case."""
    cases_blob = json.dumps({'cases': cases}, ensure_ascii=False).encode('utf-8')
    try:
        run = sandbox.run_candidate_isolated(
            CANDIDATE_RUNNER,
            inputs={'cases.json': cases_blob},
            expected_outputs=('submission.json',),
            timeout_s=CANDIDATE_TIMEOUT_S,
            argv=[str(candidate_path.resolve()), str(int(max_sim_calls))],
            copy_into_workdir=False,
        )
    except sandbox.InvalidSubmissionError as exc:
        raise CandidateRejected(str(exc)) from exc

    if run.timed_out:
        raise CandidateRejected(f'candidate timed out after {CANDIDATE_TIMEOUT_S:.0f}s')
    if run.returncode != 0:
        raise CandidateRejected(
            f'candidate subprocess exited non-zero ({run.returncode}): {run.stderr_tail[-2000:]}'
        )

    try:
        submission = sandbox.load_json_output(run)
    except sandbox.InvalidSubmissionError as exc:
        raise CandidateRejected(str(exc)) from exc

    entries = submission.get('cases')
    if not isinstance(entries, list) or len(entries) != len(cases):
        raise CandidateRejected(
            f'submission must contain one entry per case ({len(cases)} expected)'
        )

    validated: dict[str, list[float]] = {}
    reported_calls: dict[str, int] = {}
    for case, entry in zip(cases, entries):
        if not isinstance(entry, dict):
            raise CandidateRejected('each submission entry must be a JSON object')
        if entry.get('case_id') != case['case_id']:
            raise CandidateRejected(
                f"submission case order mismatch: expected {case['case_id']!r}, got {entry.get('case_id')!r}"
            )
        if 'error' in entry:
            raise CandidateRejected(f"case {case['case_id']}: candidate raised {entry['error']}")
        validated[case['case_id']] = _validate_params(entry.get('params'), case)
        calls = entry.get('sim_calls', 0)
        if isinstance(calls, bool) or not isinstance(calls, int) or calls < 0:
            raise CandidateRejected(f"case {case['case_id']}: 'sim_calls' must be a non-negative integer")
        reported_calls[case['case_id']] = calls

    return {'params': validated, 'sim_calls': reported_calls}


def evaluate_candidate(candidate_path: Path, max_sim_calls: int = 24) -> dict[str, Any]:
    cases = CANONICAL.load_cases()
    submitted = _run_candidate(candidate_path, cases, max_sim_calls)
    candidate_params = submitted['params']
    candidate_calls = submitted['sim_calls']

    per_case = []
    valid = True
    for case in cases:
        baseline_result = _canonical_baseline(case, max_sim_calls)
        baseline_metrics = CANONICAL.simulate(baseline_result['params'], case)

        params = candidate_params[case['case_id']]
        # Recomputed here, in a process the candidate never entered.
        candidate_metrics = CANONICAL.simulate(params, case)
        # Residual, and pre-existing: the call count is produced inside the
        # candidate's own process, so a candidate that tampers with the counter
        # could understate it -- worth at most the 0.002 call_penalty plus a
        # dodged budget check. The budget was never strictly enforceable anyway:
        # the candidate ships its own copy of `simulate` and can call that for
        # free without going through simulate_fn at all. What matters is that
        # the loss/feasibility half of the score -- everything that actually
        # moves it -- is recomputed above from the returned knots.
        candidate_sim_calls = int(candidate_calls[case['case_id']])

        case_valid = bool(candidate_metrics['feasible']) and candidate_sim_calls <= int(max_sim_calls)
        valid = valid and case_valid
        baseline_loss = float(baseline_metrics['loss'])
        candidate_loss = float(candidate_metrics['loss'])
        improvement_ratio = (baseline_loss - candidate_loss) / max(abs(baseline_loss), 1e-9)
        quality = math.exp(-candidate_loss / 200.0)
        call_penalty = 0.002 * float(candidate_sim_calls) / float(max_sim_calls)
        score = max(0.0, quality + 0.3 * improvement_ratio - call_penalty)
        per_case.append(
            {
                'case_id': case['case_id'],
                'baseline_loss': baseline_loss,
                'candidate_loss': candidate_loss,
                'improvement_ratio': improvement_ratio,
                'candidate_sim_calls': float(candidate_sim_calls),
                'baseline_sim_calls': float(baseline_result['sim_calls']),
                'score': score if case_valid else 0.0,
                'valid': 1.0 if case_valid else 0.0,
                'mean_temperature': float(candidate_metrics['mean_temperature']),
                'max_temperature': float(candidate_metrics['max_temperature']),
            }
        )

    combined_score = sum(item['score'] for item in per_case) / len(per_case)
    return {
        'combined_score': combined_score if valid else 0.0,
        'valid': 1.0 if valid else 0.0,
        'mean_candidate_loss': sum(item['candidate_loss'] for item in per_case) / len(per_case),
        'mean_baseline_loss': sum(item['baseline_loss'] for item in per_case) / len(per_case),
        'mean_improvement_ratio': sum(item['improvement_ratio'] for item in per_case) / len(per_case),
        'total_candidate_sim_calls': sum(item['candidate_sim_calls'] for item in per_case),
        'cases_evaluated': float(len(per_case)),
        'per_case': per_case,
    }


def _rejected_report(message: str) -> dict[str, Any]:
    return {
        'combined_score': 0.0,
        'valid': 0.0,
        'mean_candidate_loss': 0.0,
        'mean_baseline_loss': 0.0,
        'mean_improvement_ratio': 0.0,
        'total_candidate_sim_calls': 0.0,
        'cases_evaluated': 0.0,
        'candidate_error': message,
        'per_case': [],
    }


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Evaluate the real additive-manufacturing toolpath benchmark candidate')
    parser.add_argument('candidate', type=str)
    parser.add_argument('--max-sim-calls', type=int, default=24)
    parser.add_argument('--metrics-out', type=str, default=None)
    parser.add_argument('--artifacts-out', type=str, default=None)
    args = parser.parse_args()

    try:
        report = evaluate_candidate(
            Path(args.candidate).expanduser().resolve(), max_sim_calls=args.max_sim_calls
        )
    except CandidateRejected as exc:
        report = _rejected_report(str(exc))

    metrics = {key: value for key, value in report.items() if key != 'per_case'}
    _write_json(Path(args.metrics_out).resolve() if args.metrics_out else None, metrics)
    _write_json(Path(args.artifacts_out).resolve() if args.artifacts_out else None, report)
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
