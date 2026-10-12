#!/usr/bin/env python3
import json,os,subprocess,sys,tempfile
from pathlib import Path

# EVOLVE-BLOCK-START
def solve(data,out,assets):
    subprocess.run(['bash',str(assets/'solution/solve.sh'),str(data/'campaign'),str(out)],check=True)
# EVOLVE-BLOCK-END

if __name__=='__main__':
    data,out,assets=map(Path,sys.argv[1:4])
    out.mkdir(parents=True,exist_ok=True)
    solve(data,out,assets)
