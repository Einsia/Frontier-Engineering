# FixedBackboneDesign

## Overview

Design the optimal amino acid sequence for a given fixed protein backbone. This task corresponds to Case A (Fixed-Backbone Canonical Amino Acid Sequence Design) of the Agent Rosetta paper (arXiv:2603.15952, ICML 2026).

## Input

The candidate script (`scripts/init.py`) receives:

- `--prepared-input`: Path to a PDB file with the target backbone and design position annotations
- `--solution-output`: Path where the designed structure should be written

## Output

The candidate must output a PDB file at `--solution-output` containing:
1. The original backbone coordinates (unchanged)
2. Designed amino acid substitutions at specified positions
3. Only standard 20 amino acids (no non-canonical residues)

## Scoring

The evaluator uses PyRosetta's `ref2015` score function to compute:

- **total_energy**: Sum of all energy terms
- **baseline_energy**: Energy of the native (starting) sequence
- **improvement**: baseline_energy - total_energy (positive = better)
- **combined_score**: Normalized improvement = improvement / |baseline_energy|

Energy terms reported: `fa_atr`, `fa_rep`, `fa_sol`, `fa_elec`, `hbond_bb_sc`, `hbond_sc`, `p_aa_pp`, `ref`

## Constraints

- Only modify `scripts/init.py`
- Do NOT modify backbone coordinates
- Only use the 20 standard amino acids
- Output must be a valid PDB file
