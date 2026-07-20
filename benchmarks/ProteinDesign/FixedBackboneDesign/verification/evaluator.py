#!/usr/bin/env python3
"""
PyRosetta-based evaluator for FixedBackboneDesign task.

Usage (CONTRIBUTING.md test command format):
    python verification/evaluator.py scripts/init.py

Usage (step-by-step for local development):
    python verification/evaluator.py prepare --raw-task data/raw_task.json --prepared-output outputs/prepared.pdb
    python verification/evaluator.py evaluate --native outputs/prepared.pdb --candidate outputs/solution.pdb --result-output outputs/result.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

INVALID_COMBINED_SCORE = -1e18
_REFERENCE_AMINO_ACIDS = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY",
    "HIS", "ILE", "LEU", "LYS", "MET", "PHE", "PRO",
    "SER", "THR", "TRP", "TYR", "VAL",
}


# ---------------------------------------------------------------------------
# Read-only utilities
# ---------------------------------------------------------------------------

def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open() as f:
        return json.load(f)


def dump_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _hash_file(path: str | Path) -> str:
    """SHA-256 hash of a file. Used to detect unauthorized reference modifications."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Constraint verification
# ---------------------------------------------------------------------------

def _verify_constraints(native_pose, candidate_pose, design_positions: list[int]) -> tuple[bool, str]:
    """
    Verify that the candidate satisfies FixedBackboneDesign constraints.

    Checks:
    1. Same number of residues
    2. Non-design positions: same amino acid type
    3. Non-design positions: backbone atoms (N, CA, C, O) unchanged
    4. Design positions: only standard amino acids
    """
    # 1. Residue count
    if native_pose.total_residue() != candidate_pose.total_residue():
        return False, (
            f"residue count mismatch: native={native_pose.total_residue()}, "
            f"candidate={candidate_pose.total_residue()}"
        )

    design_set = set(design_positions)
    backbone_atoms = {"N", "CA", "C", "O"}

    for i in range(1, native_pose.total_residue() + 1):
        native_res = native_pose.residue(i)
        candidate_res = candidate_pose.residue(i)

        if i in design_set:
            # Design positions: only standard amino acids allowed
            res_name = candidate_res.name3()
            if res_name not in _REFERENCE_AMINO_ACIDS:
                return False, f"non-standard amino acid at design position {i}: {res_name}"
        else:
            # Non-design positions: amino acid type must be preserved
            if native_res.name3() != candidate_res.name3():
                return False, (
                    f"unexpected mutation at non-design position {i}: "
                    f"{native_res.name3()} -> {candidate_res.name3()}"
                )

            # Backbone atom coordinates must not move
            for atom_name in backbone_atoms:
                if native_res.has(atom_name) and candidate_res.has(atom_name):
                    native_xyz = native_res.xyz(atom_name)
                    candidate_xyz = candidate_res.xyz(atom_name)
                    dist = native_xyz.distance(candidate_xyz)
                    if dist > 0.01:
                        return False, (
                            f"backbone atom {atom_name} moved at position {i}: "
                            f"{dist:.6f} Å (threshold: 0.01 Å)"
                        )

    return True, ""


# ---------------------------------------------------------------------------
# Prepare: load raw_task.json, load PDB, create a prepared reference PDB
# ---------------------------------------------------------------------------

def prepare(raw_task_path: str | Path, prepared_output: str | Path) -> None:
    """
    Read raw_task.json, load the PDB, and output a prepared PDB file.
    The prepared PDB serves as the reference (native) structure.
    """
    import pyrosetta
    pyrosetta.init(silent=True)
    pyrosetta.rosetta.basic.random.init_random_generators(42, "mt19937")

    task = load_json(raw_task_path)
    task_root = Path(raw_task_path).resolve().parent.parent
    pdb_path = Path(task["pdb_path"])
    if not pdb_path.is_absolute():
        pdb_path = task_root / pdb_path

    design_positions = task["design_positions"]
    task_config = task.get("task_config", {})

    # Load the native structure
    pose = pyrosetta.pose_from_file(str(pdb_path))

    # Repack native side chains to get a baseline energy
    scorefxn = pyrosetta.get_fa_scorefxn()
    tf = pyrosetta.rosetta.core.pack.task.TaskFactory()
    tf.push_back(pyrosetta.rosetta.core.pack.task.operation.RestrictToRepacking())
    packer = pyrosetta.rosetta.protocols.minimization_packing.PackRotamersMover()
    packer.score_function(scorefxn)
    packer.task_factory(tf)
    packer.apply(pose)

    baseline_energy = scorefxn(pose)

    # Dump the repacked native pose as the prepared reference PDB
    output_path = Path(prepared_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pose.dump_pdb(str(output_path))

    meta = {
        "baseline_energy": round(baseline_energy, 6),
        "design_positions": design_positions,
        "n_design_positions": len(design_positions),
        "pdb_source": task.get("pdb_id", str(pdb_path.name)),
        "native_sequence": task.get("native_sequence", ""),
        "energy_function": task.get("energy_function", "ref2015"),
        "task_config": task_config,
    }
    meta_path = Path(prepared_output).with_suffix(".meta.json")
    dump_json(meta_path, meta)
    print(f"[evaluator] Prepared reference: {output_path}")
    print(f"[evaluator] Baseline energy: {baseline_energy:.4f}")


# ---------------------------------------------------------------------------
# Evaluate: score the candidate PDB against the native reference
# ---------------------------------------------------------------------------

def evaluate_candidate(
    native_pdb: str | Path,
    candidate_pdb: str | Path,
    design_positions: list[int] | None = None,
) -> dict[str, Any]:
    """
    Score a designed PDB using PyRosetta ref2015 and verify task constraints.

    Returns:
        dict with keys: valid, combined_score, total_energy, native_energy,
                        improvement, and individual energy terms
    """
    import pyrosetta
    pyrosetta.init(silent=True)
    pyrosetta.rosetta.basic.random.init_random_generators(42, "mt19937")

    scorefxn = pyrosetta.get_fa_scorefxn()

    # Score native
    native_pose = pyrosetta.pose_from_file(str(native_pdb))
    native_energy = scorefxn(native_pose)

    # Score candidate
    candidate_pose = pyrosetta.pose_from_file(str(candidate_pdb))

    # Verify task constraints before scoring
    if design_positions is not None:
        valid, msg = _verify_constraints(native_pose, candidate_pose, design_positions)
        if not valid:
            return {
                "valid": False,
                "combined_score": INVALID_COMBINED_SCORE,
                "error_message": msg,
                "native_energy": round(native_energy, 6),
                "total_energy": 0.0,
            }

    candidate_energy = scorefxn(candidate_pose)

    # Collect metrics
    metrics: dict[str, Any] = {"valid": True}
    metrics["native_energy"] = round(native_energy, 6)
    metrics["total_energy"] = round(candidate_energy, 6)
    metrics["improvement"] = round(native_energy - candidate_energy, 6)

    if abs(native_energy) > 1e-6:
        metrics["combined_score"] = round((native_energy - candidate_energy) / abs(native_energy), 6)
    else:
        metrics["combined_score"] = 0.0

    # Energy terms
    native_energies = native_pose.energies()
    candidate_energies = candidate_pose.energies()
    score_types = [
        (pyrosetta.rosetta.core.scoring.ScoreType.fa_atr, "fa_atr"),
        (pyrosetta.rosetta.core.scoring.ScoreType.fa_rep, "fa_rep"),
        (pyrosetta.rosetta.core.scoring.ScoreType.fa_sol, "fa_sol"),
        (pyrosetta.rosetta.core.scoring.ScoreType.fa_elec, "fa_elec"),
        (pyrosetta.rosetta.core.scoring.ScoreType.hbond_bb_sc, "hbond_bb_sc"),
        (pyrosetta.rosetta.core.scoring.ScoreType.hbond_sc, "hbond_sc"),
        (pyrosetta.rosetta.core.scoring.ScoreType.p_aa_pp, "p_aa_pp"),
        (pyrosetta.rosetta.core.scoring.ScoreType.ref, "ref"),
    ]
    for st, name in score_types:
        try:
            metrics[f"native_{name}"] = round(float(native_energies.total_energies()[st]), 6)
            metrics[name] = round(float(candidate_energies.total_energies()[st]), 6)
        except Exception:
            pass

    # NaN/Inf check
    for key in ("total_energy", "native_energy"):
        val = metrics.get(key, 0.0)
        if math.isnan(val) or math.isinf(val):
            metrics["valid"] = False
            metrics["combined_score"] = INVALID_COMBINED_SCORE

    return metrics


def evaluate(
    native_pdb: str | Path,
    candidate_pdb: str | Path,
    result_output: str | Path,
    design_positions: list[int] | None = None,
) -> None:
    """Evaluate designed sequence and write result JSON."""
    metrics = evaluate_candidate(native_pdb, candidate_pdb, design_positions)
    dump_json(result_output, metrics)
    print(f"[evaluator] total_energy={metrics.get('total_energy', 0):.4f}  "
          f"improvement={metrics.get('improvement', 0):.4f}  "
          f"valid={metrics.get('valid', False)}")


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_candidate_and_evaluate(script_path: str | Path) -> int:
    """Full automatic pipeline matching CONTRIBUTING.md test command format."""
    evaluator_dir = Path(__file__).resolve().parent
    task_dir = evaluator_dir.parent
    raw_task = task_dir / "data" / "raw_task.json"
    outputs_dir = task_dir / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    prepared_pdb = outputs_dir / "prepared.pdb"
    solution_pdb = outputs_dir / "solution.pdb"
    metrics_path = task_dir / "metrics.json"

    # Step 1: Prepare
    print(f"[evaluator] Preparing from {raw_task}")
    prepare(raw_task, prepared_pdb)

    # Record reference file hash before candidate runs
    ref_hash_before = _hash_file(prepared_pdb)

    # Read design positions for constraint verification
    meta_path = prepared_pdb.with_suffix(".pdb.meta.json")
    if not meta_path.exists():
        meta_path = prepared_pdb.with_suffix(".meta.json")
    design_positions: list[int] = []
    if meta_path.exists():
        meta = load_json(meta_path)
        design_positions = list(meta.get("design_positions", []))

    # Step 2: Run candidate
    print(f"[evaluator] Running candidate: {script_path}")
    try:
        result = subprocess.run(
            [sys.executable, str(script_path),
             "--prepared-input", str(prepared_pdb),
             "--solution-output", str(solution_pdb)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(task_dir),
        )
        print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        if result.stderr:
            print(f"[evaluator] candidate stderr:\n{result.stderr[-2000:]}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("[evaluator] ERROR: candidate timed out (300s)")
        metrics = {
            "valid": False,
            "combined_score": INVALID_COMBINED_SCORE,
            "total_energy": 0.0,
            "error_message": "candidate timed out",
        }
        dump_json(metrics_path, metrics)
        print(json.dumps(metrics))
        return 1
    except FileNotFoundError:
        print(f"[evaluator] ERROR: candidate script not found: {script_path}")
        return 1

    # Verify reference file was not modified by candidate
    ref_hash_after = _hash_file(prepared_pdb)
    if ref_hash_before != ref_hash_after:
        print("[evaluator] ERROR: reference file was modified by candidate")
        metrics = {
            "valid": False,
            "combined_score": INVALID_COMBINED_SCORE,
            "error_message": "reference file was modified by candidate",
        }
        dump_json(metrics_path, metrics)
        print(json.dumps(metrics))
        return 1

    # Step 3: Evaluate with constraint verification
    print(f"[evaluator] Evaluating designed structure")
    metrics = evaluate_candidate(prepared_pdb, solution_pdb, design_positions)
    metrics["returncode"] = result.returncode
    if result.returncode != 0:
        metrics["valid"] = False
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["error_message"] = f"candidate returned non-zero exit code: {result.returncode}"

    # Step 4: Write metrics.json
    dump_json(metrics_path, metrics)
    print(json.dumps(metrics))
    return 0 if metrics.get("valid", False) else 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) == 2 and not sys.argv[1].startswith("--"):
        return run_candidate_and_evaluate(sys.argv[1])

    parser = argparse.ArgumentParser(description="PyRosetta evaluator for FixedBackboneDesign")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_prep = subparsers.add_parser("prepare", help="Prepare reference PDB from raw task")
    p_prep.add_argument("--raw-task", required=True)
    p_prep.add_argument("--prepared-output", required=True)

    p_eval = subparsers.add_parser("evaluate", help="Evaluate designed PDB")
    p_eval.add_argument("--native", required=True)
    p_eval.add_argument("--candidate", required=True)
    p_eval.add_argument("--result-output", required=True)
    p_eval.add_argument("--design-positions", nargs="*", type=int, default=None,
                        help="Optional list of allowed design positions for constraint check")

    args = parser.parse_args()

    if args.command == "prepare":
        prepare(args.raw_task, args.prepared_output)
    elif args.command == "evaluate":
        evaluate(args.native, args.candidate, args.result_output, args.design_positions)
    return 0


if __name__ == "__main__":
    sys.exit(main())
