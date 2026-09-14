"""Verify actual experiment observations, not candidate-written histories."""
import importlib
import sys
from pathlib import Path

import pytest

pytest.importorskip('summit')
ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / 'benchmarks' / 'ReactionOptimisation'
sys.path.insert(0, str(DOMAIN))
from shared.isolated import run_candidate

TASKS = ('mit_case1_mixed', 'snar_multiobjective', 'reizman_suzuki_pareto', 'dtlz2_pareto')


@pytest.mark.parametrize('name', TASKS)
def test_original_baseline_preserves_observations(name):
    task = importlib.import_module(name + '.task')
    baseline = importlib.import_module(name + '.baseline.solution')
    expected = baseline.solve(seed=0, budget=2)
    result = run_candidate(task, DOMAIN / name / 'baseline' / 'solution.py', 0, 2)
    assert len(result['history']) == 2
    assert result['summary']['score'] == pytest.approx(expected['summary']['score'], abs=1e-8)


def test_forged_history_without_experiments_is_rejected(tmp_path):
    from mit_case1_mixed import task
    candidate = tmp_path / 'fake.py'
    candidate.write_text("def solve(seed, budget):\n    return {'algorithm_name':'fake', 'history':[{'y':1}], 'summary':{'score':100}}\n")
    with pytest.raises(ValueError, match='no observations'):
        run_candidate(task, candidate, 0, 2)


def test_forged_objectives_do_not_replace_actual_observations(tmp_path):
    from mit_case1_mixed import task
    source = (DOMAIN / task.TASK_NAME / 'baseline' / 'solution.py').read_text()
    source = source.replace('history.append(record)', "history.append({**record, 'y': 1.0})")
    candidate = tmp_path / 'fake.py'
    candidate.write_text(source)
    result = run_candidate(task, candidate, 0, 1)
    expected = task.evaluate(task.create_benchmark(), {k:result['history'][0][k] for k in task.INPUT_NAMES})
    assert result['history'][0]['y'] == pytest.approx(expected['y'])
    assert result['summary']['score'] < 100.0


def test_budget_violation_cannot_be_hidden_by_catching_error(tmp_path):
    from mit_case1_mixed import task
    candidate = tmp_path / 'overbudget.py'
    candidate.write_text('''
from mit_case1_mixed import task
import numpy as np

def solve(seed, budget):
    experiment = task.create_benchmark()
    proposal = task.sample_candidate(np.random.default_rng(seed))
    for _ in range(budget + 1):
        try:
            task.evaluate(experiment, proposal)
        except Exception:
            pass
    return {'algorithm_name': 'caught'}
''')
    with pytest.raises(ValueError, match='budget exceeded'):
        run_candidate(task, candidate, 0, 1)
