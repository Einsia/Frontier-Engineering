"""Regression coverage for candidate file access, lifetime and score propagation."""
import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'benchmarks' / '_shared'))
import candidate_sandbox as sandbox


def test_restricted_candidate_reads_only_declared_inputs(tmp_path):
    secret = tmp_path / 'resources_truth' / 'answer'
    secret.parent.mkdir()
    secret.write_text('held-out answer')
    public = tmp_path / 'resources_cache' / 'input'
    public.parent.mkdir()
    public.write_text('allowed input')
    candidate = tmp_path / 'candidate.py'
    candidate.write_text(f'''
import json
from pathlib import Path
p = Path({str(public)!r})
assert p.read_text() == 'allowed input'
try:
    p.parents[1].joinpath('resources_truth/answer').read_text()
except (FileNotFoundError, PermissionError):
    Path('submission.json').write_text('{{"hidden": true}}')
else:
    raise RuntimeError('truth was visible')
''')
    run = sandbox.run_candidate_isolated(candidate, timeout_s=10,
        readonly_paths=(public,), expected_outputs=('submission.json',))
    assert run.ok
    assert sandbox.load_json_output(run) == {'hidden': True}


def test_candidate_network_cannot_reach_host_loopback(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        candidate = tmp_path / 'candidate.py'
        candidate.write_text(f'''
import socket
from pathlib import Path
try:
    socket.create_connection(('127.0.0.1', {port}), timeout=1)
except OSError:
    Path('result').write_text('blocked')
else:
    raise RuntimeError('host network visible')
''')
        run = sandbox.run_candidate_isolated(candidate, timeout_s=10,
            readonly_paths=(), expected_outputs=('result',))
        assert run.ok and run.read_output_bytes('result') == b'blocked'


def test_detached_descendant_dies_before_return(tmp_path):
    marker = tmp_path / 'late_write'
    candidate = tmp_path / 'candidate.py'
    candidate.write_text(f'''
import os, time
from pathlib import Path
if os.fork() == 0:
    os.setsid()
    time.sleep(0.4)
    Path({str(marker)!r}).write_text('escaped')
    os._exit(0)
Path('result').write_text('done')
''')
    run = sandbox.run_candidate_isolated(candidate, timeout_s=5, expected_outputs=('result',))
    assert run.ok
    time.sleep(0.6)
    assert not marker.exists()


TASKS = ('disruption_eoqd', 'finite_horizon_dp', 'general_meio',
         'joint_replenishment', 'tree_gsm_safety_stock')


@pytest.mark.parametrize('task', TASKS)
@pytest.mark.parametrize('produce_comparison', (True, False))
def test_inventory_runner_propagates_rejection(task, produce_comparison, tmp_path):
    (tmp_path / 'frontier_eval').mkdir()
    (tmp_path / 'verification').mkdir()
    runner = tmp_path / 'frontier_eval' / 'run_eval.py'
    shutil.copy(ROOT / 'benchmarks' / 'InventoryOptimization' / task / 'frontier_eval' / 'run_eval.py', runner)
    record = {'baseline_final_score': 0.0, 'candidate_error': 'candidate rejected'}
    source = ("import json\nfrom pathlib import Path\n"
              f"Path('output/comparison.json').write_text(json.dumps({record!r}))\n")
    (tmp_path / 'verification' / 'evaluate.py').write_text(source if produce_comparison else 'pass\n')
    result = subprocess.run([sys.executable, str(runner)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / 'metrics.json').read_text())['valid'] == 0.0


@pytest.mark.parametrize('task,source,expected', [
    ('disruption_eoqd', 'def solve(cfg): return 1, 23, 1\n', {'order_quantity': 23}),
    ('finite_horizon_dp', 'def solve(mean, sd): return [1,2], [3,4]\n', {'reorder_points':[1,2], 'order_up_to_levels':[3,4]}),
    ('general_meio', 'def solve(): return {10: 12}\n', {'base_stock': {'10':12}}),
    ('joint_replenishment', 'def solve(): return {"base_cycle_time": 0.2, "order_multiples": [1]}\n', {'base_cycle_time':0.2, 'order_multiples':[1]}),
    ('tree_gsm_safety_stock', 'def solve(): return {1: 2}\n', {'cst':{'1':2}}),
])
def test_inventory_original_function_interface(task, source, expected, tmp_path):
    candidate = tmp_path / 'old.py'
    candidate.write_text(source)
    run = sandbox.run_inventory_candidate(candidate, task, timeout_s=10,
        inputs={'config.json': b'{"demand_mean":[1,2], "demand_sd":[1,1]}'},
        expected_outputs=('submission.json',))
    assert run.ok and sandbox.load_json_output(run) == expected


@pytest.mark.parametrize('duration', [float('nan'), float('inf'), 0.0, -1.0])
def test_kernel_rejects_invalid_diagnostic_times(duration, tmp_path):
    from kernel_isolation import KernelTaskConfig, _score
    cfg = KernelTaskConfig('test', tmp_path, 'unused')
    metrics, _ = _score(cfg, {}, {}, [{'index':0, 'ok':True, 'errors':[],
        'durations_ns':[duration], 'wall_ns':100_000, 'flush_wall_ns':20_000}])
    assert metrics['valid'] == 0.0 and metrics['combined_score'] == 0.0


def test_kernel_score_uses_parent_time_including_output_delivery(tmp_path):
    from kernel_isolation import KernelTaskConfig, _score
    cfg = KernelTaskConfig('test', tmp_path, 'unused')
    scores = []
    for reported in (1, 1000, 90000):
        metrics, _ = _score(cfg, {}, {}, [{'index':0, 'ok':True, 'errors':[],
            'durations_ns':[reported], 'wall_ns':100_000, 'flush_wall_ns':20_000}])
        assert metrics['valid'] == 1.0
        scores.append(metrics['combined_score'])
    assert scores == pytest.approx([1e9 / 120000] * 3)


def test_bare_interpreter_name_does_not_expose_working_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name: sys.executable if name == "test-python" else original_which(name))
    command = sandbox.namespace_command(["test-python", "-c", "pass"], tmp_path, ())
    assert command[command.index("--") + 1] == sys.executable
    mounts = [command[i + 1] for i, arg in enumerate(command) if arg == "--ro-bind"]
    assert str(tmp_path.parent) not in mounts


def test_restricted_candidate_can_use_private_shared_memory(tmp_path):
    candidate = tmp_path / "locks.py"
    candidate.write_text("from multiprocessing import Lock\nfrom pathlib import Path\nwith Lock():\n    Path('result').write_text('ok')\n")
    run = sandbox.run_candidate_isolated(candidate, timeout_s=10, readonly_paths=(), expected_outputs=('result',))
    assert run.ok and run.read_output_bytes('result') == b'ok'


def test_restricted_runtime_supports_system_compiler(tmp_path):
    if shutil.which("gcc") is None:
        pytest.skip("system C compiler unavailable")
    candidate = tmp_path / "compile.py"
    candidate.write_text("import subprocess\nfrom pathlib import Path\n"
        "Path('probe.c').write_text('int main(void) { return 0; }')\n"
        "subprocess.run(['/usr/bin/gcc', 'probe.c', '-o', 'probe'], check=True)\n"
        "subprocess.run(['./probe'], check=True)\n"
        "Path('result').write_text('compiled')\n")
    run = sandbox.run_candidate_isolated(candidate, readonly_paths=(), timeout_s=20,
        expected_outputs=('result',))
    assert run.ok, run.stderr_tail
    assert run.read_output_bytes('result') == b'compiled'
