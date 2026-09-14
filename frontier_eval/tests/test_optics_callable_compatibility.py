"""The original Optics callables return designs, never trusted scores/models."""
import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'benchmarks' / '_shared'))
from candidate_sandbox import run_optics_candidate


def npz(**values):
    buf = io.BytesIO()
    np.savez(buf, **values)
    return buf.getvalue()


def test_original_phase_callable_receives_canonical_problem(tmp_path):
    candidate = tmp_path / 'old.py'
    candidate.write_text('''
import numpy as np

def build_problem():
    raise AssertionError('candidate problem factory must not be used')
def solve_baseline(problem):
    assert problem['cfg']['seed'] == 7
    return {'phase': np.zeros_like(problem['target_amp']), 'metrics': {'score': 1e9}}
''')
    run = run_optics_candidate(candidate, 'phase', timeout_s=20,
        inputs={'problem.json':json.dumps({'cfg':{'seed':7}, 'decision_variable':{'key':'phase'}}).encode(),
                'problem.npz':npz(target_amp=np.ones((3,3)))}, expected_outputs=('submission.json',))
    assert run.ok
    assert json.loads(run.read_output_bytes('submission.json')) == {'phase':np.zeros((3,3)).tolist()}


@pytest.mark.parametrize('supplied_mask', [False, True])
def test_legacy_fourier_receives_dark_mask_from_canonical_target(tmp_path, supplied_mask):
    candidate = tmp_path / 'legacy_fourier.py'
    expected_mask = [[False, True], [True, False]] if supplied_mask else [[True, False], [False, True]]
    candidate.write_text(f"""
import numpy as np

def build_problem():
    raise AssertionError('candidate problem factory must not be used')
def solve_baseline(problem):
    np.testing.assert_array_equal(problem['dark_mask'], {expected_mask!r})
    assert problem['dark_mask'].dtype == np.bool_
    return np.zeros_like(problem['target_amp'])
""")
    arrays = {'target_amp': np.array([[0.0, 0.03], [0.04, 0.02]])}
    if supplied_mask:
        arrays['dark_mask'] = np.asarray(expected_mask)
    run = run_optics_candidate(candidate, 'phase', timeout_s=20,
        inputs={'problem.json':json.dumps({'task':'task02_fourier_pattern_holography',
                    'cfg':{'seed':0}, 'decision_variable':{'key':'phase'}}).encode(),
                'problem.npz':npz(**arrays)}, expected_outputs=('submission.json',))
    assert run.ok, run.stderr_tail
    assert json.loads(run.read_output_bytes('submission.json')) == {'phase':[[0.0,0.0],[0.0,0.0]]}


def test_original_controller_preserves_actuator_recurrence(tmp_path):
    candidate = tmp_path / 'old.py'
    candidate.write_text('''
import numpy as np

def compute_dm_commands(slopes, reconstructor, control_model, prev_commands, max_voltage):
    return prev_commands + slopes
''')
    run = run_optics_candidate(candidate, 'adaptive', timeout_s=20,
        inputs={'problem.npz':npz(slopes=np.ones((3,2)), reconstructor=np.eye(2),
            n_act=2, max_voltage=10, actuator_lag=0.5)}, expected_outputs=('submission.npz',))
    assert run.ok
    with np.load(io.BytesIO(run.read_output_bytes('submission.npz'))) as data:
        np.testing.assert_allclose(data['commands'], [[1,1],[1.5,1.5],[2,2]])


@pytest.mark.parametrize('attribute,key,spec', [('phase','phases',{}), ('thickness','thickness',{'wavelengths':[1,2]})])
def test_original_holographic_system_is_reduced_to_parameters(tmp_path, attribute, key, spec):
    candidate = tmp_path / 'old.py'
    candidate.write_text(f'''
from types import SimpleNamespace
import numpy as np

def solve(spec, device, seed):
    return {{'system': [SimpleNamespace({attribute}=np.ones((2,2)))],
            'input_field': object(), 'target_fields': object(), 'score': 1e9}}
''')
    run = run_optics_candidate(candidate, 'holographic', timeout_s=20,
        inputs={'problem.json':json.dumps(spec).encode()}, expected_outputs=('submission.npz',))
    assert run.ok
    with np.load(io.BytesIO(run.read_output_bytes('submission.npz'))) as data:
        assert data.files == [key]
        np.testing.assert_array_equal(data[key], np.ones((1,2,2)))


def test_legacy_holographic_preserves_learning_rate_and_official_budget(tmp_path):
    candidate = tmp_path / 'legacy.py'
    candidate.write_text("import numpy as np\n"
        "def make_default_spec(): return {'shape': 64, 'lr': 0.25, 'steps': 15}\n"
        "def solve(spec, device, seed):\n"
        "    assert spec['shape'] == 72\n"
        "    assert spec['steps'] == 24\n"
        "    assert spec['lr'] == 0.25\n"
        "    return {'phases': np.zeros((1, 72, 72))}\n")
    run = run_optics_candidate(candidate, 'holographic', timeout_s=20,
        inputs={'problem.json':json.dumps({'shape':72, 'steps':24, 'lr':0.075}).encode()},
        expected_outputs=('submission.npz',))
    assert run.ok, run.stderr_tail
    with np.load(io.BytesIO(run.read_output_bytes('submission.npz'))) as data:
        assert data['phases'].shape == (1,72,72)
