#!/usr/bin/env python3
"""
FixedBackboneDesign baseline solution.

This file is the target of agent evolution. Code inside EVOLVE-BLOCK
can be modified by the agent; everything outside is read-only.

CLI contract:
    --prepared-input <path>   Path to prepared PDB (with design position metadata)
    --solution-output <path>  Path to write the designed PDB
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Read-only utilities (CLI contract, I/O)
# ---------------------------------------------------------------------------

def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open() as f:
        return json.load(f)


def dump_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def load_design_positions(prepared_pdb: str | Path) -> list[int]:
    """
    Read design positions from the meta JSON accompanying the prepared PDB.
    The meta file is at the same path but with .meta.json extension.
    """
    p = Path(prepared_pdb)
    meta_path = p.with_suffix(".pdb.meta.json")
    if not meta_path.exists():
        meta_path = p.with_suffix(".meta.json")
    if meta_path.exists():
        meta = load_json(meta_path)
        return list(meta.get("design_positions", []))
    raise FileNotFoundError(
        f"Meta file not found at {p.with_suffix('.pdb.meta.json')} or {p.with_suffix('.meta.json')}. "
        f"Ensure evaluator.prepare() was called first."
    )


# EVOLVE-BLOCK-START
# ---------------------------------------------------------------------------
# Editable region — agent may modify the design algorithm below
# ---------------------------------------------------------------------------

import pyrosetta
from pyrosetta.rosetta.core.pack.task import TaskFactory
from pyrosetta.rosetta.core.pack.task.operation import PreventRepacking
from pyrosetta.rosetta.protocols.minimization_packing import PackRotamersMover


def design_sequence(
    prepared_pdb: str | Path,
    solution_output: str | Path,
    design_positions: list[int],
) -> dict[str, Any]:
    """
    Fixed-backbone sequence design using PyRosetta PackRotamersMover.

    This is a basic baseline: one round of design with default options.
    Improvements could include:
    - Multiple design rounds with iterations
    - Monte Carlo simulated annealing
    - Backbone flexibility (small shear moves)
    - Custom rotamer sampling with extra rotamers
    """
    pyrosetta.init(silent=True)
    pyrosetta.rosetta.basic.random.init_random_generators(42, "mt19937")

    # Load the prepared PDB
    pose = pyrosetta.pose_from_file(str(prepared_pdb))
    scorefxn = pyrosetta.get_fa_scorefxn()

    # Create a PackerTask for sequence design
    # By default, all positions are designable with all 20 canonical AAs
    tf = TaskFactory()
    task = tf.create_task_and_apply_taskoperations(pose)

    # Configure per-residue behavior
    for i in range(1, pose.total_residue() + 1):
        if i in design_positions:
            # Allow repacking (side chain optimization) at design positions
            # Default behavior: all 20 AAs allowed
            pass
        else:
            # Do not change non-design positions
            task.nonconst_residue_task(i).prevent_repacking()

    # Run Packer with the configured task (not the factory)
    packer = PackRotamersMover()
    packer.score_function(scorefxn)
    packer.task(task)
    packer.apply(pose)

    # Score the designed pose
    final_energy = scorefxn(pose)

    # Write output PDB
    output_path = Path(solution_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pose.dump_pdb(str(output_path))

    # Collect metadata
    result = {
        "final_energy": round(float(final_energy), 6),
        "n_designed_positions": len(design_positions),
        "solver": "packrotamers_single_round",
        "design_positions": sorted(design_positions),
    }
    return result


# EVOLVE-BLOCK-END
# ---------------------------------------------------------------------------
# End of editable region
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Read-only main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="FixedBackboneDesign baseline — design protein sequence"
    )
    parser.add_argument("--prepared-input", required=True, help="Prepared PDB file")
    parser.add_argument("--solution-output", required=True, help="Output PDB path")
    args = parser.parse_args()

    design_positions = load_design_positions(args.prepared_input)

    result = design_sequence(
        prepared_pdb=args.prepared_input,
        solution_output=args.solution_output,
        design_positions=design_positions,
    )

    # Print summary
    print(f"[init] Designed {result['n_designed_positions']} positions, "
          f"final energy: {result['final_energy']:.4f}")


if __name__ == "__main__":
    main()
