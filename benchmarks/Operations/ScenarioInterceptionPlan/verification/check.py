"""Strict integer verifier. Only trusted verifier data defines the problem."""
import argparse
import json
from pathlib import Path

# Replaced by the authoring generator. These are provisional replay baselines,
# not claimed historical competition best scores.
LIMIT = 762


def evaluate(case_path, solution_path):
    data = json.loads(Path(case_path).read_text())
    result = {'valid': False, 'objective': None, 'limit': LIMIT, 'reward': 0}
    try:
        raw = Path(solution_path).read_bytes()
        if len(raw) > 128 * len(data['options']) + 1024:
            raise ValueError('solution file exceeds format bound')
        def no_duplicate_keys(pairs):
            d = {}
            for k, v in pairs:
                if k in d:
                    raise ValueError('duplicate JSON key')
                d[k] = v
            return d
        submission = json.loads(raw, object_pairs_hook=no_duplicate_keys)
        if type(submission) is not dict or set(submission) != {'selected'}:
            raise ValueError('expected exactly the selected field')
        selected = submission['selected']
        if type(selected) is not list or any(type(x) is not str for x in selected):
            raise ValueError('selected must be a list of string identifiers')
        picked = set(selected)
        if len(picked) != len(selected):
            raise ValueError('duplicate option')
        available = set(data['options'])
        if not picked <= available:
            raise ValueError('unknown option')
        if data['kind'] == 'monitoring':
            covered = set(picked)
            for u, v in data['links']:
                if u in picked:
                    covered.add(v)
                if v in picked:
                    covered.add(u)
            if covered != available:
                raise ValueError('some facilities are not monitored')
        else:
            # Check every scenario, including repeated identical rows.
            if any(not any(x in picked for x in row) for row in data['scenarios']):
                raise ValueError('some scenarios are not detected')
        result.update(valid=True, objective=len(picked), reward=int(len(picked) <= LIMIT))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result['error'] = str(exc)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--case', default='/tests/data/campaign.json')
    p.add_argument('--solution', default='/app/results/selection.json')
    p.add_argument('--out', default='/logs/verifier')
    a = p.parse_args()
    result = evaluate(a.case, a.solution)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_text(json.dumps(result, indent=2))
    (out / 'reward.txt').write_text(str(result['reward']) + '\n')
    print(json.dumps(result))
