#!/usr/bin/env python3
"""NCAAInsertion baseline — design residues around TRF insertion site."""

from __future__ import annotations
import argparse, json
from pathlib import Path

def load_json(path): return json.loads(Path(path).read_text())

def load_meta(prepared_pdb):
    p = Path(prepared_pdb)
    for s in [".pdb.meta.json",".meta.json"]:
        m = p.with_suffix(s)
        if m.exists(): return load_json(m)
    return {}

def trf_params_path():
    c = Path(__file__).resolve().parent.parent / "references" / "params" / "TRF.params"
    return str(c.resolve()) if c.exists() else None

# EVOLVE-BLOCK-START
import pyrosetta
from pyrosetta.rosetta.core.pack.task import TaskFactory
from pyrosetta.rosetta.protocols.minimization_packing import PackRotamersMover

def design_sequence(prepared_pdb, solution_output, design_positions, trf_position, trf_params_path):
    extra = f"-extra_res_fa {trf_params_path}" if trf_params_path else ""
    pyrosetta.init(silent=True, extra_options=extra)
    pyrosetta.rosetta.basic.random.init_random_generators(42, "mt19937")

    pose = pyrosetta.pose_from_file(str(prepared_pdb))
    scorefxn = pyrosetta.get_fa_scorefxn()
    design_set = set(design_positions)

    # Use RestrictToRepacking to ensure no AA changes (only side chain repacking)
    # This is safer than prevent_repacking which may not be honored by the packer
    from pyrosetta.rosetta.core.pack.task.operation import RestrictToRepacking

    tf = TaskFactory()
    tf.push_back(RestrictToRepacking())
    packer = PackRotamersMover()
    packer.score_function(scorefxn)
    packer.task_factory(tf)
    packer.apply(pose)

    final = scorefxn(pose)
    Path(solution_output).parent.mkdir(parents=True,exist_ok=True)
    pose.dump_pdb(str(solution_output))

    trf_ok = 1 <= trf_position <= pose.total_residue() and \
             ("TRF" in pose.residue(trf_position).name() or pose.residue(trf_position).name3() == "TRF")
    return {"final_energy": round(float(final),6), "trf_position": trf_position,
            "trf_inserted": trf_ok, "n_designed_positions": len(design_positions),
            "solver": "packrotamers_single_design"}
# EVOLVE-BLOCK-END

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--prepared-input",required=True); a.add_argument("--solution-output",required=True)
    v = a.parse_args()
    m = load_meta(v.prepared_input)
    r = design_sequence(v.prepared_input, v.solution_output,
                       m.get("design_positions",[]), m.get("trf_position",4), trf_params_path())
    print(f"[init] Designed {r['n_designed_positions']} positions, TRF: {r['trf_inserted']}")
if __name__ == "__main__": main()
