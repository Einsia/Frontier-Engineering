"""Strict submission schema plus archived official constraint/objective checkers."""
import argparse,json,math,re,subprocess,sys,tempfile
from pathlib import Path
from format import maintenance_native,deployment_native,decode_solution

LIMIT = 2743.5078649237475
TOLERANCE = 1e-08

def unique_object(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('Duplicate JSON key')
        result[k]=v
    return result

def evaluate(data,solution,tools):
    records={}
    for f in sorted(Path(data).glob('*.json')):
        try:
            case=json.loads(f.read_text());answer_path=Path(solution)/f.name
            if answer_path.stat().st_size>32*1024*1024:raise ValueError('Oversized submission')
            answer=json.loads(answer_path.read_text(),object_pairs_hook=unique_object)
            if type(answer) is not dict:raise ValueError('Expected JSON object')
            text=decode_solution(case,answer)
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);(p/'answer').write_text(text)
                if case['kind']=='maintenance':
                    (p/'input.json').write_text(json.dumps(maintenance_native(case)))
                    cmd=[sys.executable,str(Path(tools)/'official_checker.py'),str(p/'input.json'),str(p/'answer')]
                else:
                    model,initial=deployment_native(case);(p/'model').write_text(model);(p/'initial').write_text(initial)
                    cmd=[str(Path(tools)/'checker'),str(p/'model'),str(p/'initial'),str(p/'answer')]
                q=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
                raw=q.stdout+q.stderr
                if q.returncode or 'ERROR' in raw:raise ValueError('Official checker rejected solution: '+raw[-1200:])
                if case['kind']=='maintenance':
                    match=re.search(r'Total objective .*:\s*(\S+)',q.stdout)
                    value=float(match.group(1)) if match else None
                else:
                    if 'Solution is valid.' not in raw:raise ValueError('Official checker found infeasible assignment')
                    match=re.search(r'(?i)cost[^\d]*(\d+)',q.stdout)
                    value=int(match.group(1)) if match else None
                if value is None or not math.isfinite(value):raise ValueError('No finite objective')
                records[f.stem]={'valid':True,'objective':value}
        except Exception as exc:records[f.stem]={'valid':False,'error':str(exc)}
    valid=bool(records) and all(x['valid'] for x in records.values())
    objective=sum(x['objective'] for x in records.values()) if valid else None
    return {'valid':valid,'objective':objective,'limit':LIMIT,'tolerance':TOLERANCE,
            'reward':int(valid and objective<=LIMIT+TOLERANCE),'cases':records}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',default='/tests/data');p.add_argument('--solution',default='/app/results');p.add_argument('--out',default='/logs/verifier');p.add_argument('--tools',default='/opt/official');a=p.parse_args()
    report=evaluate(a.data,a.solution,a.tools);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'reward.txt').write_text(str(report['reward'])+'\n');print(json.dumps(report))
