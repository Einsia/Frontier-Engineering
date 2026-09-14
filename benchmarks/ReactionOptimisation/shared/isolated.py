"""Run optimization code separately; own experiment calls, budget and history."""
from __future__ import annotations

import importlib
import json
import math
import socket
import sys
import tempfile
import threading
from pathlib import Path

from shared.utils import to_python

_RUNNER = r'''
import importlib, importlib.util, json, os, socket, sys
from pathlib import Path
root = Path('repo').resolve()
os.environ['FRONTIER_ENGINEERING_ROOT'] = str(root)
domain = root / 'benchmarks' / 'ReactionOptimisation'
sys.path.insert(0, str(domain))
name, endpoint, seed, budget = sys.argv[1:]
task = importlib.import_module(name + '.task')

def request(candidate):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.connect(endpoint)
        stream = conn.makefile('rwb')
        stream.write((json.dumps(candidate, default=lambda x: x.item()) + '\n').encode())
        stream.flush()
        response = json.loads(stream.readline())
    if 'error' in response:
        raise RuntimeError(response['error'])
    return response['record']

class RemoteExperiment:
    def __init__(self, *args, **kwargs):
        self._records = []
    def run_experiments(self, conditions, *args, **kwargs):
        import pandas as pd
        from summit.utils.dataset import DataSet
        records = []
        for _, row in conditions.iterrows():
            proposal = {n: row[(n, 'DATA')] if (n, 'DATA') in row.index else row[n]
                        for n in task.INPUT_NAMES}
            records.append(request(proposal))
        self._records.extend(records)
        return DataSet.from_df(pd.DataFrame(records))
    @property
    def data(self):
        import pandas as pd
        from summit.utils.dataset import DataSet
        return DataSet.from_df(pd.DataFrame(self._records))

task.create_benchmark = RemoteExperiment
path = domain / name / 'baseline' / 'solution.py'
spec = importlib.util.spec_from_file_location('candidate_solution', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = module.solve(seed=int(seed), budget=int(budget))
# The candidate supplies metadata only. Its history/summary are never scored.
Path('submission.json').write_text(json.dumps({'algorithm_name': str(result.get('algorithm_name', 'candidate'))}))
'''


def run_candidate(task, candidate_path: Path, seed: int, budget: int) -> dict:
    root = next(p for p in Path(__file__).resolve().parents if (p / 'benchmarks' / '_shared').is_dir())
    sys.path.insert(0, str(root / 'benchmarks' / '_shared'))
    import candidate_sandbox as sandbox
    if budget <= 0:
        raise ValueError('budget must be positive')
    # Instantiate the real model before any candidate code runs.
    experiment = task.create_benchmark()
    history, failures = [], []
    domain = root / 'benchmarks' / 'ReactionOptimisation'
    inputs = {'repo/frontier_eval/.keep': b'',
              f'repo/benchmarks/ReactionOptimisation/{task.TASK_NAME}/task.py': Path(task.__file__).read_bytes(),
              f'repo/benchmarks/ReactionOptimisation/{task.TASK_NAME}/baseline/solution.py': Path(candidate_path).read_bytes()}
    for path in (domain / 'shared').glob('*.py'):
        if path.name != 'isolated.py':
            inputs[f'repo/benchmarks/ReactionOptimisation/shared/{path.name}'] = path.read_bytes()
    with tempfile.TemporaryDirectory(prefix='fe_reaction_rpc_') as tmp:
        endpoint = str(Path(tmp) / 'experiment.sock')
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(endpoint)
        server.listen(4)
        server.settimeout(0.1)
        stop = threading.Event()

        def serve():
            while not stop.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with conn:
                    conn.settimeout(1.0)
                    try:
                        stream = conn.makefile('rwb')
                        raw = stream.readline(65537)
                        if len(raw) > 65536:
                            raise ValueError('experiment request too large')
                        candidate = json.loads(raw)
                        if not isinstance(candidate, dict) or set(candidate) != set(task.INPUT_NAMES):
                            raise ValueError('experiment input names do not match the task')
                        if len(history) >= budget:
                            raise ValueError('experiment budget exceeded')
                        for name, bounds in getattr(task, 'BOUNDS', {n: (0.0, 1.0) for n in task.INPUT_NAMES}).items():
                            value = candidate[name]
                            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not bounds[0] <= value <= bounds[1]:
                                raise ValueError(f'invalid experiment input {name}')
                        for name, choices in getattr(task, 'CATEGORIES', {}).items():
                            if candidate[name] not in choices:
                                raise ValueError(f'invalid category {name}')
                        observed = task.evaluate(experiment, candidate)
                        record = {name: observed[name] for name in task.INPUT_NAMES + task.OBJECTIVE_NAMES}
                        for name in task.OBJECTIVE_NAMES:
                            if not math.isfinite(float(record[name])):
                                raise ValueError('non-finite experiment observation')
                        history.append(record)
                        response = {'record': record}
                    except Exception as exc:
                        failures.append(str(exc))
                        response = {'error': str(exc)}
                    try:
                        conn.sendall((json.dumps(response, default=to_python, allow_nan=False) + '\n').encode())
                    except OSError:
                        pass

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        wrapper = Path(tmp) / 'runner.py'
        wrapper.write_text(_RUNNER)
        try:
            run = sandbox.run_candidate_isolated(
                wrapper, inputs=inputs, expected_outputs=('submission.json',),
                argv=(task.TASK_NAME, endpoint, str(seed), str(budget)),
                timeout_s=600, readonly_paths=(Path(endpoint),),
                env_allowlist=('PATH', 'LANG', 'LC_ALL', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS'),
            )
        finally:
            stop.set()
            server.close()
            worker.join(timeout=5)
        if not run.ok or failures or not history:
            raise ValueError(f'invalid candidate experiment run: {failures or run.stderr_tail or "no observations"}')
        metadata = sandbox.load_json_output(run)
    return {'task_name': task.TASK_NAME, 'algorithm_name': metadata.get('algorithm_name', 'candidate'),
            'seed': seed, 'budget': budget, 'history': history, 'summary': task.summarize(history)}
