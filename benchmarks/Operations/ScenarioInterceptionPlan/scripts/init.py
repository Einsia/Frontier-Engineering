#!/usr/bin/env python3
import json,os,subprocess,sys,tempfile
from pathlib import Path

# EVOLVE-BLOCK-START
def solve(data,out,assets):
    sys.path.insert(0,str(assets/'environment/tools'))
    from format import read_case, encode_solution
    w=assets/'solution/src'
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);binary=p/'solver'
        cpp=sorted((w/'solver/lib').glob('*.cpp'))+sorted((w/'solver/tools').glob('*.cpp'))
        subprocess.run(['g++','-std=c++20','-O2','-I'+str(w)]+list(map(str,cpp))+['-o',str(binary)],check=True)
        case=data/'campaign.json';_,native=read_case(case)
        (p/'input').write_text(native)
        with (p/'input').open('rb') as inp,(p/'answer').open('wb') as output:
            subprocess.run([str(binary)],stdin=inp,stdout=output,cwd=p,env=dict(os.environ,SOLVER_ITERATIONS='1000000',SOLVER_WORK_BUDGET='1000000',OMP_NUM_THREADS='1'),check=True)
        encode_solution(case,p/'answer',out/'selection.json')
# EVOLVE-BLOCK-END

if __name__=='__main__':
    data,out,assets=map(Path,sys.argv[1:4])
    out.mkdir(parents=True,exist_ok=True)
    solve(data,out,assets)
