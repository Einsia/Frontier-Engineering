"""Candidate-side adapters for the original Optics callable interfaces.

Only design arrays leave this process. Candidate models, targets and metrics
never cross into the scorer.
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import numpy as np


def array(value):
    if hasattr(value, 'detach'):
        value = value.detach().cpu().numpy()
    if isinstance(value, (list, tuple)):
        return np.asarray([array(v) for v in value])
    return np.asarray(value)


def main():
    mode = sys.argv[1]
    sys.argv = ['candidate.py']
    output = Path('submission.json' if mode == 'phase' else 'submission.npz')
    # Holographic scripts may publish directly in their __main__ block while
    # keeping an unrelated solve() stub. Original function-only solvers have
    # no entry-point block, so they are adapted below if no file was produced.
    scope = runpy.run_path('candidate.py',
        run_name='__main__' if mode == 'holographic' else 'optics_candidate')
    if output.is_file():
        return
    # Preserve current file-protocol entry points, including their final
    # projections. Legacy function-only programs use the adapters below.
    if callable(scope.get('_main')):
        scope['_main']()
        return
    if mode == 'phase' and not callable(scope.get('solve_baseline')) and callable(scope.get('main')):
        scope['main']()
        return
    if mode == 'phase':
        meta = json.loads(Path('problem.json').read_text())
        with np.load('problem.npz', allow_pickle=False) as data:
            problem = {'cfg': meta['cfg'], **{k:data[k] for k in data.files}}
        if meta.get('task') == 'task02_fourier_pattern_holography' and 'dark_mask' not in problem:
            # Legacy Fourier solvers used this mask from their problem factory.
            # Derive it from the scorer's target without calling that factory.
            problem['dark_mask'] = problem['target_amp'] < 0.03
        fn = scope.get('solve_baseline', scope.get('solve'))
        if callable(fn):
            result = fn(problem)
            key = meta['decision_variable']['key']
            decision = result[key] if isinstance(result, dict) else result
            output.write_text(json.dumps({key:array(decision).tolist()}))
            return
    elif mode == 'adaptive':
        with np.load('problem.npz', allow_pickle=False) as data:
            problem = {k:data[k] for k in data.files}
        model = {k[4:]:(v if v.ndim else v.item()) for k,v in problem.items() if k.startswith('cm__')}
        fusion = 'slopes_multi' in problem
        fn = scope.get('fuse_and_compute_dm_commands' if fusion else 'compute_dm_commands')
        if callable(fn):
            stream = problem['slopes_multi' if fusion else 'slopes']
            previous = np.zeros(int(problem['n_act']))
            commands = []
            lag = float(problem.get('actuator_lag', 0))
            for i, slopes in enumerate(stream):
                if 'episode_length' in problem and i % int(problem['episode_length']) == 0:
                    previous = np.zeros_like(previous)
                command = array(fn(slopes, problem['reconstructor'], model,
                    None if fusion else previous, max_voltage=float(problem['max_voltage'])))
                commands.append(command.copy())
                applied = command
                if 'rate_limit' in problem:
                    limit = float(problem['rate_limit'])
                    applied = previous + np.clip(command - previous, -limit, limit)
                previous = lag * previous + (1 - lag) * applied
            np.savez(output, commands=np.asarray(commands))
            return
    elif mode == 'holographic':
        fn = scope.get('solve')
        if callable(fn):
            spec = json.loads(Path('problem.json').read_text())
            # The old verifier kept the candidate's learning rate, while
            # overriding its step budget. Preserve that algorithm parameter;
            # physical dimensions, targets and budget remain scorer-owned.
            defaults_fn = scope.get('make_default_spec')
            if callable(defaults_fn):
                defaults = defaults_fn()
                if isinstance(defaults, dict) and 'lr' in defaults:
                    spec['lr'] = defaults['lr']
            result = fn(spec=spec, device='cpu', seed=0)
            values = {key:array(result[key]) for key in ('phases','thickness','phase_x','phase_y') if key in result}
            if not values and 'phase_x_layers' in result:
                values = {'phase_x':array(result['phase_x_layers']), 'phase_y':array(result['phase_y_layers'])}
            if not values and 'system' in result:
                layers = list(result['system'])
                attr = 'thickness' if 'wavelengths' in spec else 'phase'
                values = {'thickness' if attr == 'thickness' else 'phases':array([getattr(layer,attr) for layer in layers])}
            if not values:
                raise ValueError('solve() returned no physical design parameters')
            np.savez(output, **values)
            return
    # Standalone file producers remain supported. No returned score is used.
    fn = scope.get('main', scope.get('_main'))
    if callable(fn):
        fn()
    else:
        runpy.run_path('candidate.py', run_name='__main__')


if __name__ == '__main__':
    main()
