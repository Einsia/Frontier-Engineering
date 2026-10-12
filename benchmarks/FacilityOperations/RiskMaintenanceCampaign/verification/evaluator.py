#!/usr/bin/env python3
"""Run a candidate in isolation, then score only its generated data."""
import hashlib,json,math,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'environment/data'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'verification'))
import check

def repo_root():
    if os.environ.get('FRONTIER_ENGINEERING_ROOT'):
        return Path(os.environ['FRONTIER_ENGINEERING_ROOT']).resolve()
    for parent in ROOT.parents:
        if (parent/'benchmarks/_shared/candidate_sandbox.py').exists():return parent
    raise RuntimeError('Run inside the Frontier-Engineering checkout or set FRONTIER_ENGINEERING_ROOT')
sys.path.insert(0,str(repo_root()/'benchmarks/_shared'))
import candidate_sandbox as sandbox
EXPECTED=['campaign-01.json', 'campaign-02.json']

def main():
    candidate=Path(sys.argv[1]).resolve()
    result={'valid':False,'combined_score':-1e18}
    try:
        run=sandbox.run_candidate_isolated(candidate,expected_outputs=['outputs/'+n for n in EXPECTED],timeout_s=900,argv=[str(DATA),'outputs',str(ROOT)],readonly_paths=[DATA,ROOT/'solution',ROOT/'environment/tools'] if (ROOT/'environment/tools').exists() else [DATA,ROOT/'solution'],rlimits={'AS':16*1024**3,'FSIZE':128*1024**2},python=sys.executable)
        if not run.ok:raise ValueError('Candidate failed: '+run.stderr_tail[-2000:])
        with tempfile.TemporaryDirectory(prefix='fe_score_') as td:
            output=Path(td)
            hashes={}
            for name in EXPECTED:
                blob=run.read_output_bytes('outputs/'+name)
                (output/name).write_bytes(blob);hashes[name]=hashlib.sha256(blob).hexdigest()
            result=check.evaluate(DATA,output,ROOT/'verification/official')
            objective=result.get('objective')
        if not result.get('valid'):raise ValueError(str(result.get('error',result)))
        if objective is None or not math.isfinite(objective):raise ValueError('Nonfinite objective')
        result={'valid':True,'objective':objective,'combined_score':-float(objective),'cases':result.get('cases',{}),'artifact_sha256':hashes}
    except Exception as exc:
        result={'valid':False,'combined_score':-1e18,'error':str(exc)}
    (ROOT/'metrics.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,allow_nan=False))
    return 0 if result['valid'] else 1
if __name__=='__main__':raise SystemExit(main())
