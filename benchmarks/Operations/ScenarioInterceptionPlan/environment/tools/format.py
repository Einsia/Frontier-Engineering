"""Public conversion helpers: all indexes derive solely from the released input."""
import json
from pathlib import Path


def read_case(path):
    d = json.loads(Path(path).read_text())
    ids = d['options']
    if len(ids) != len(set(ids)) or any(type(x) is not str for x in ids):
        raise ValueError('option identifiers must be unique strings')
    index = {x: i + 1 for i, x in enumerate(ids)}
    if d['kind'] == 'monitoring':
        edges = [(index[u], index[v]) for u, v in d['links']]
        header = f'p ds {len(ids)} {len(edges)}'
    elif d['kind'] == 'interception':
        edges = [tuple(index[x] for x in row) for row in d['scenarios']]
        if any(not x for x in edges):
            raise ValueError('uncoverable empty scenario')
        header = f'p hs {len(ids)} {len(edges)}'
    else:
        raise ValueError('unknown kind')
    return d, header + '\n' + ''.join(' '.join(map(str, e)) + '\n' for e in edges)


def encode_solution(case_path, native_path, output_path):
    d, _ = read_case(case_path)
    values = list(map(int, Path(native_path).read_text().split()))
    if not values or values[0] != len(values) - 1:
        raise ValueError('native solution size mismatch')
    picked = values[1:]
    if len(picked) != len(set(picked)) or any(v < 1 or v > len(d['options']) for v in picked):
        raise ValueError('native solution identifiers invalid')
    # Canonical order is specified by the input's option list, independent of set order.
    result = {'selected': [d['options'][v - 1] for v in sorted(picked)]}
    Path(output_path).write_text(json.dumps(result, separators=(',', ':')) + '\n')
