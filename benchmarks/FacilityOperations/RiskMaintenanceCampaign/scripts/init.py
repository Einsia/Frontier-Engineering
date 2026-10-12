#!/usr/bin/env python3
import json,os,subprocess,sys,tempfile
from pathlib import Path

# EVOLVE-BLOCK-START
def solve(data,out,assets):
    sys.path.insert(0,str(assets/'environment/tools'))
    from format import maintenance_native, encode
    w=assets/'solution/src'
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);binary=p/'solver'
        cpp=[w/'search/examples/roadef2020_main.cpp',w/'search/examples/roadef2020.cpp',w/'problems/orproblems/roadef2020.cpp',w/'tools/optimizationtools/info.cpp',w/'simdjson/simdjson.cpp']
        subprocess.run(['g++','-std=c++17','-O3','-DNDEBUG']+['-I'+str(w/d) for d in ['search','problems','tools','simdjson','include']]+list(map(str,cpp))+['-lboost_program_options','-pthread','-o',str(binary)],check=True)
        for case in sorted(data.glob('*.json')):
            (p/'input.json').write_text(json.dumps(maintenance_native(json.loads(case.read_text()))))
            subprocess.run([str(binary),'-p',str(p/'input.json'),'-o',str(p/'answer'),'-s','0','-x','1','-y','1'],cwd=p,env=dict(os.environ,SOLVER_NODES='1000',OMP_NUM_THREADS='1'),check=True)
            encode(case,p/'answer',out/case.name)
# EVOLVE-BLOCK-END

if __name__=='__main__':
    data,out,assets=map(Path,sys.argv[1:4])
    out.mkdir(parents=True,exist_ok=True)
    solve(data,out,assets)
