"""Public, deterministic conversions. Contains no reference solutions."""
import json
from pathlib import Path

MAINTENANCE_KEYS = {'capacity_pools':'Resources', 'calendar_groups':'Seasons',
    'operations':'Interventions', 'incompatibilities':'Exclusions',
    'period_count':'T', 'scenarios_per_period':'Scenarios_number',
    'risk_quantile':'Quantile', 'mean_risk_weight':'Alpha',
    'reference_runtime_minutes':'ComputationTime'}


def maintenance_native(case):
    return {MAINTENANCE_KEYS[k]: v for k, v in case.items() if k in MAINTENANCE_KEYS}


def deployment_native(d):
    pools=d['capacity_pools'];hosts=d['hosts'];services=d['services'];work=d['workloads']
    hi={x['id']:i for i,x in enumerate(hosts)}
    si={x['id']:i for i,x in enumerate(services)}
    ri={x['id']:i for i,x in enumerate(pools)}
    ni={v:i for i,v in enumerate(d['neighborhood_order'])}
    li={v:i for i,v in enumerate(d['location_order'])}
    rows=[[len(pools)]]+[[int(x['transient']),x['load_weight']] for x in pools]
    rows.append([len(hosts)])
    rows += [[ni[x['neighborhood']],li[x['location']]]+x['capacity']+x['safety_capacity']+x['migration_costs'] for x in hosts]
    rows.append([len(services)])
    for x in services:rows.append([x['min_locations'],len(x['depends_on'])]+[si[v] for v in x['depends_on']])
    rows.append([len(work)])
    rows += [[si[x['service']]]+x['demand']+[x['migration_cost']] for x in work]
    rows.append([len(d['balance_costs'])])
    rows += [[ri[x['first']],ri[x['second']],x['target'],x['weight']] for x in d['balance_costs']]
    rows.append(d['migration_weights'])
    model='\n'.join(' '.join(map(str,row)) for row in rows)+'\n'
    initial=' '.join(str(hi[x['initial_host']]) for x in work)+'\n'
    return model,initial


def encode(case, native_file, output):
    d=json.loads(Path(case).read_text())
    if d['kind']=='maintenance':
        starts={}
        for line in Path(native_file).read_text().splitlines():
            key,value=line.split();assert key not in starts;starts[key]=int(value)
        result={'starts':starts}
    else:
        assignments=list(map(int,Path(native_file).read_text().split()))
        assert len(assignments)==len(d['workloads'])
        result={'placements':{x['id']:d['hosts'][v]['id'] for x,v in zip(d['workloads'],assignments)}}
    Path(output).write_text(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')


def decode_solution(d, answer):
    if d['kind']=='maintenance':
        starts=answer.get('starts')
        if not isinstance(starts,dict) or set(starts)!=set(d['operations']):raise ValueError('Need exactly one start per operation')
        for k,v in starts.items():
            if type(v) is not int or not 1<=v<=d['period_count']:raise ValueError('Invalid start period')
        return '\n'.join(f'{k} {starts[k]}' for k in d['operations'])+'\n'
    placements=answer.get('placements');hi={x['id']:i for i,x in enumerate(d['hosts'])}
    if not isinstance(placements,dict) or set(placements)!={x['id'] for x in d['workloads']}:raise ValueError('Need exactly one host per workload')
    if any(type(v) is not str or v not in hi for v in placements.values()):raise ValueError('Unknown host')
    return ' '.join(str(hi[placements[x['id']]]) for x in d['workloads'])+'\n'
