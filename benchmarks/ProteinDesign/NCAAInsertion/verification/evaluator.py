#!/usr/bin/env python3
"""
PyRosetta-based evaluator for NCAAInsertion task (Case B).

Inserts TRF (1-formyl-tryptophan), a non-canonical amino acid,
into fixed protein backbones and evaluates design quality.

The task supports multiple protein scaffolds (configured in raw_task.json).
Each protein gets TRF inserted at a specified position, with surrounding
residues designed. The total score is the sum across all proteins.

Usage (CONTRIBUTING.md test command format):
    python verification/evaluator.py scripts/init.py

Usage (step-by-step):
    python verification/evaluator.py prepare --raw-task data/raw_task.json --prepared-output ...
    python verification/evaluator.py evaluate --native ... --candidate ... --result-output ...
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

INVALID_COMBINED_SCORE = -1e18
_PYROSETTA_INITIALIZED = False


def _ensure_pyrosetta_init(trf_params_path: str | None = None) -> None:
    """Initialize PyRosetta once with fixed seed. Subsequent calls are no-ops."""
    global _PYROSETTA_INITIALIZED
    if not _PYROSETTA_INITIALIZED:
        import pyrosetta
        extra = f"-extra_res_fa {trf_params_path}" if trf_params_path else ""
        pyrosetta.init(silent=True, extra_options=extra)
        pyrosetta.rosetta.basic.random.init_random_generators(42, "mt19937")
        _PYROSETTA_INITIALIZED = True


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open() as f:
        return json.load(f)


def dump_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _resolve_trf_params(task_dir: Path) -> str:
    return str((task_dir / "references" / "params" / "TRF.params").resolve())


# ---------------------------------------------------------------------------
# Utility: hash file for tamper detection
# ---------------------------------------------------------------------------

def _hash_file(path: str | Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Constraint verification
# ---------------------------------------------------------------------------

_REFERENCE_AA = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY",
    "HIS", "ILE", "LEU", "LYS", "MET", "PHE", "PRO",
    "SER", "THR", "TRP", "TYR", "VAL",
}


def _verify_constraints(
    native_pose, candidate_pose,
    design_positions: list[int],
    trf_position: int | None = None,
) -> tuple[bool, str]:
    """Verify candidate satisfies fixed-backbone constraints."""
    if native_pose.total_residue() != candidate_pose.total_residue():
        return False, f"residue count mismatch"

    backbone = {"N", "CA", "C", "O"}
    for i in range(1, native_pose.total_residue() + 1):
        nat = native_pose.residue(i)
        cand = candidate_pose.residue(i)
        if nat.name3() != cand.name3() and i not in set(design_positions) and i != trf_position:
            return False, f"unexpected mutation at position {i}: {nat.name3()} -> {cand.name3()}"
        for atm in backbone:
            if nat.has(atm) and cand.has(atm):
                d = nat.xyz(atm).distance(cand.xyz(atm))
                if d > 0.01:
                    return False, f"backbone atom {atm} moved at position {i}: {d:.6f} Å"

    # TRF position check (allow either native or candidate to have TRF)
    if trf_position and 1 <= trf_position <= native_pose.total_residue():
        cand = candidate_pose.residue(trf_position)
        if cand.name3() not in ("TRF",) and "TRF" not in cand.name():
            return False, f"TRF missing at position {trf_position}: found {cand.name3()}"

    return True, ""


# ---------------------------------------------------------------------------
# Prepare a single protein: load PDB, repack native, place TRF, dump
# ---------------------------------------------------------------------------

def prepare_single_protein(
    pdb_path: str | Path,
    trf_position: int,
    trf_params_path: str,
    prepared_output: str | Path,
) -> dict[str, Any]:
    """
    Load a protein PDB, repack side chains (baseline), place TRF, and dump.
    Returns metadata dict with baseline energy and configuration.
    """
    import pyrosetta

    _ensure_pyrosetta_init(trf_params_path)

    pose = pyrosetta.pose_from_file(str(pdb_path))
    scorefxn = pyrosetta.get_fa_scorefxn()

    # Repack native side chains for baseline energy
    tf = pyrosetta.rosetta.core.pack.task.TaskFactory()
    tf.push_back(pyrosetta.rosetta.core.pack.task.operation.RestrictToRepacking())
    packer = pyrosetta.rosetta.protocols.minimization_packing.PackRotamersMover()
    packer.score_function(scorefxn)
    packer.task_factory(tf)
    packer.apply(pose)
    baseline_energy = scorefxn(pose)

    # Place TRF at the target position
    if 1 <= trf_position <= pose.total_residue():
        res_set = pyrosetta.rosetta.core.chemical.ChemicalManager.get_instance().residue_type_set("fa_standard")
        trf_res_type = res_set.name_map("TRF")
        trf_res = pyrosetta.rosetta.core.conformation.Residue(trf_res_type, True)
        pose.replace_residue(trf_position, trf_res, True)

    # Dump prepared PDB
    output_path = Path(prepared_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pose.dump_pdb(str(output_path))

    return {
        "baseline_energy": round(baseline_energy, 6),
        "trf_position": trf_position,
        "n_residues": pose.total_residue(),
    }


# ---------------------------------------------------------------------------
# Evaluate a single designed PDB
# ---------------------------------------------------------------------------

def evaluate_candidate(
    native_pdb: str | Path,
    candidate_pdb: str | Path,
    trf_position: int,
    trf_params_path: str,
    design_positions: list[int] | None = None,
) -> dict[str, Any]:
    """Score a designed PDB containing TRF. Checks TRF presence and energy."""
    import pyrosetta

    _ensure_pyrosetta_init(trf_params_path)
    scorefxn = pyrosetta.get_fa_scorefxn()

    native_pose = pyrosetta.pose_from_file(str(native_pdb))
    candidate_pose = pyrosetta.pose_from_file(str(candidate_pdb))

    # Constraint verification before scoring
    if design_positions is not None:
        valid, msg = _verify_constraints(native_pose, candidate_pose, design_positions, trf_position)
        if not valid:
            return {
                "valid": False,
                "combined_score": INVALID_COMBINED_SCORE,
                "native_energy": round(scorefxn(native_pose), 6),
                "total_energy": 0.0,
                "error_message": msg,
            }

    candidate_energy = scorefxn(candidate_pose)
    native_energy = scorefxn(native_pose)

    # Validate TRF
    trf_ok = False
    trf_msg = ""
    if 1 <= trf_position <= candidate_pose.total_residue():
        res = candidate_pose.residue(trf_position)
        trf_name = res.name3()
        trf_ok = trf_name == "TRF" or "TRF" in res.name()
        trf_msg = f"TRF at position {trf_position}: {trf_name}" if trf_ok else f"Expected TRF at pos {trf_position}, found {trf_name}"
    else:
        trf_msg = f"Position {trf_position} out of range"

    # Extract energy terms
    candidate_energies = candidate_pose.energies()
    native_energies = native_pose.energies()

    metrics: dict[str, Any] = {
        "valid": False,
        "trf_present": trf_ok,
        "trf_check": trf_msg,
        "native_energy": round(native_energy, 6),
        "total_energy": round(candidate_energy, 6),
        "improvement": round(native_energy - candidate_energy, 6),
    }

    # Individual energy terms
    score_types_info = {
        pyrosetta.rosetta.core.scoring.ScoreType.fa_atr: "fa_atr",
        pyrosetta.rosetta.core.scoring.ScoreType.fa_rep: "fa_rep",
        pyrosetta.rosetta.core.scoring.ScoreType.fa_sol: "fa_sol",
        pyrosetta.rosetta.core.scoring.ScoreType.fa_elec: "fa_elec",
        pyrosetta.rosetta.core.scoring.ScoreType.hbond_bb_sc: "hbond_bb_sc",
        pyrosetta.rosetta.core.scoring.ScoreType.hbond_sc: "hbond_sc",
        pyrosetta.rosetta.core.scoring.ScoreType.p_aa_pp: "p_aa_pp",
        pyrosetta.rosetta.core.scoring.ScoreType.ref: "ref",
    }
    for st, name in score_types_info.items():
        try:
            metrics[name] = round(float(candidate_energies.total_energies()[st]), 6)
        except Exception:
            metrics[name] = 0.0

    all_finite = all(
        not (math.isnan(metrics.get(k, 0)) or math.isinf(metrics.get(k, 0)))
        for k in ["total_energy", "native_energy"]
    )

    if trf_ok and all_finite:
        metrics["valid"] = True
        if abs(native_energy) > 1e-6:
            metrics["combined_score"] = round((native_energy - candidate_energy) / abs(native_energy), 6)
        else:
            metrics["combined_score"] = 0.0
    else:
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["error"] = trf_msg if not trf_ok else "non-finite energy"

    return metrics


# ---------------------------------------------------------------------------
# Full pipeline: multi-protein, single candidate script
# ---------------------------------------------------------------------------

def run_candidate_and_evaluate(script_path: str | Path) -> int:
    """
    Full automatic pipeline across all proteins:
    1. Read raw_task.json
    2. For each protein: prepare → candidate → evaluate
    3. Aggregate scores across proteins
    """
    evaluator_dir = Path(__file__).resolve().parent
    task_dir = evaluator_dir.parent
    raw_task_path = task_dir / "data" / "raw_task.json"
    outputs_dir = task_dir / "outputs"
    outputs_dir.mkdir(exist_ok=True)
    trf_params_path = _resolve_trf_params(task_dir)

    task = load_json(raw_task_path)
    proteins = task.get("proteins", [])
    trf_params_path = _resolve_trf_params(task_dir)

    if not proteins:
        print("[evaluator] ERROR: no proteins defined in raw_task.json")
        return 1

    print(f"[evaluator] NCAA task: {len(proteins)} proteins")
    print(f"[evaluator] TRF params: {trf_params_path}")

    all_metrics = []
    total_success = True
    total_improvement = 0.0
    total_native = 0.0
    total_candidate = 0.0

    for idx, protein in enumerate(proteins):
        pid = protein.get("id", f"protein_{idx}")
        pdb_rel = protein["pdb"]
        trf_pos = protein["trf_position"]
        design_pos = protein.get("design_positions", [])

        pdb_path = task_dir / pdb_rel
        prepared_pdb = outputs_dir / f"prepared_{pid}.pdb"
        solution_pdb = outputs_dir / f"solution_{pid}.pdb"

        print(f"\n{'='*50}")
        print(f"[evaluator] Protein {idx+1}/{len(proteins)}: {pid}")
        print(f"[evaluator]   PDB: {pdb_rel}")
        print(f"[evaluator]   TRF position: {trf_pos}")
        print(f"[evaluator]   Design positions ({len(design_pos)}): {design_pos}")

        # Step 1: Prepare (repack native + place TRF)
        print(f"[evaluator] Preparing {pid}...")
        meta = prepare_single_protein(
            pdb_path=pdb_path,
            trf_position=trf_pos,
            trf_params_path=trf_params_path,
            prepared_output=prepared_pdb,
        )
        print(f"[evaluator]   Baseline energy: {meta['baseline_energy']:.4f}")

        # Record reference hash before candidate runs
        ref_hash_before = _hash_file(prepared_pdb)

        # Step 2: Run candidate
        print(f"[evaluator] Running candidate for {pid}...")
        try:
            result = subprocess.run(
                [sys.executable, str(script_path),
                 "--prepared-input", str(prepared_pdb),
                 "--solution-output", str(solution_pdb)],
                capture_output=True, text=True, timeout=300, cwd=str(task_dir),
            )
            if result.stdout:
                last_line = [l for l in result.stdout.strip().split("\n") if l][-1:]
                if last_line:
                    print(f"[evaluator]   Candidate: {last_line[0]}")
            if result.returncode != 0:
                print(f"[evaluator]   WARNING: candidate returned {result.returncode}")
        except subprocess.TimeoutExpired:
            err_metrics = {"valid": False, "combined_score": INVALID_COMBINED_SCORE, "error": "timeout"}
            all_metrics.append(err_metrics)
            total_success = False
            continue
        except FileNotFoundError:
            print(f"[evaluator] ERROR: candidate script not found: {script_path}")
            return 1

        # Verify reference was not modified by candidate
        if _hash_file(prepared_pdb) != ref_hash_before:
            err_metrics = {"valid": False, "combined_score": INVALID_COMBINED_SCORE, "error": "reference modified"}
            all_metrics.append(err_metrics)
            total_success = False
            print(f"[evaluator]   ERROR: reference file was modified")
            continue

        # Step 3: Evaluate with constraint verification
        print(f"[evaluator] Evaluating {pid}...")
        metrics = evaluate_candidate(
            native_pdb=prepared_pdb,
            candidate_pdb=solution_pdb,
            trf_position=trf_pos,
            trf_params_path=trf_params_path,
            design_positions=design_pos,
        )
        metrics["returncode"] = result.returncode
        if result.returncode != 0:
            metrics["valid"] = False
            metrics["combined_score"] = INVALID_COMBINED_SCORE
            total_success = False

        trf_check = metrics.get('trf_present', False)
        print(f"[evaluator]   TRF: {'✅' if trf_check else '❌'}")
        te = metrics.get('total_energy', 0)
        ne = metrics.get('native_energy', 0)
        print(f"[evaluator]   Energy: {te:.4f}  (native: {ne:.4f})")

        all_metrics.append(metrics)
        total_native += ne
        total_candidate += te
        total_improvement += metrics.get('improvement', 0)

    # Aggregate results
    total_valid = all(m.get("valid", False) for m in all_metrics)
    total_trf = all(m.get("trf_present", False) for m in all_metrics)

    aggregated = {
        "valid": total_valid,
        "trf_present": total_trf,
        "n_proteins": len(proteins),
        "n_successful": sum(1 for m in all_metrics if m.get("valid", False)),
        "native_energy": round(total_native, 6),
        "total_energy": round(total_candidate, 6),
        "improvement": round(total_improvement, 6),
    }

    if total_valid and abs(total_native) > 1e-6:
        aggregated["combined_score"] = round(total_improvement / abs(total_native), 6)
    else:
        aggregated["combined_score"] = INVALID_COMBINED_SCORE

    # Per-protein details
    aggregated["proteins"] = []
    for idx, (p, m) in enumerate(zip(proteins, all_metrics)):
        aggregated["proteins"].append({
            "id": p.get("id", f"protein_{idx}"),
            "trf_position": p["trf_position"],
            "design_positions": p.get("design_positions", []),
            "valid": m.get("valid", False),
            "trf_present": m.get("trf_present", False),
            "native_energy": m.get("native_energy", 0),
            "total_energy": m.get("total_energy", 0),
            "improvement": m.get("improvement", 0),
        })

    # Write metrics.json
    metrics_path = task_dir / "metrics.json"
    dump_json(metrics_path, aggregated)
    print(json.dumps(aggregated))

    return 0 if total_valid else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) == 2 and not sys.argv[1].startswith("--"):
        return run_candidate_and_evaluate(sys.argv[1])

    parser = argparse.ArgumentParser(description="PyRosetta evaluator for NCAAInsertion")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_prep = subparsers.add_parser("prepare", help="Prepare reference PDB")
    p_prep.add_argument("--raw-task", required=True)
    p_prep.add_argument("--prepared-output", required=True)

    p_eval = subparsers.add_parser("evaluate", help="Evaluate designed PDB")
    p_eval.add_argument("--native", required=True)
    p_eval.add_argument("--candidate", required=True)
    p_eval.add_argument("--result-output", required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        # For single-file prepare, read raw_task and prepare first protein
        task = load_json(args.raw_task)
        task_root = Path(args.raw_task).resolve().parent.parent
        trf_params_path = _resolve_trf_params(task_root)
        protein = task["proteins"][0]
        pdb_path = task_root / protein["pdb"]
        meta = prepare_single_protein(
            pdb_path=pdb_path,
            trf_position=protein["trf_position"],
            trf_params_path=trf_params_path,
            prepared_output=args.prepared_output,
        )
        dump_json(Path(args.prepared_output).with_suffix(".pdb.meta.json"), meta)
        print(f"[evaluator] Prepared, baseline energy: {meta['baseline_energy']:.4f}")
    elif args.command == "evaluate":
        # Read trf_position from meta file
        meta_path = Path(args.native).with_suffix(".pdb.meta.json")
        trf_pos = 4
        trf_params_path = _resolve_trf_params(Path(__file__).resolve().parent.parent)
        if meta_path.exists():
            meta = load_json(meta_path)
            trf_pos = meta.get("trf_position", 4)

        metrics = evaluate_candidate(
            native_pdb=args.native,
            candidate_pdb=args.candidate,
            trf_position=trf_pos,
            trf_params_path=trf_params_path,
        )
        dump_json(args.result_output, metrics)
        print(f"[evaluator] total_energy={metrics['total_energy']:.4f}  "
              f"trf_present={metrics['trf_present']}  valid={metrics['valid']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
