# NCAAInsertion — Non-Canonical Amino Acid Insertion Design

## Overview

Insert the non-canonical amino acid **TRF (1-formyl-tryptophan)** at specified positions in fixed protein backbones, and redesign surrounding residues to accommodate it. This task covers **3 distinct protein scaffolds** to comprehensively evaluate an agent's ability to handle non-canonical amino acids.

This task corresponds to **Case B** of the Agent Rosetta paper (arXiv:2603.15952, ICML 2026).

## Biological Background

### What Are Non-Canonical Amino Acids (NCAAs)?

Proteins are typically built from 20 standard amino acids. However, nature also uses hundreds of "non-canonical" amino acids that offer chemical functionalities beyond the standard set:

| Function | Example | Application |
|:---------|:--------|:------------|
| **Fluorescent probes** | Dansyl, p-cyanophenylalanine | Tracking protein localization and dynamics in cells |
| **Photocrosslinking** | p-benzoyl-phenylalanine | Capturing transient protein-protein interactions |
| **Novel catalysis** | Selenocysteine, pyrrolysine | Engineering enzymes with new reaction mechanisms |
| **Improved pharmacokinetics** | Fluorinated amino acids | Enhancing stability and half-life of peptide therapeutics |

### Why This Task Matters

Most ML-based protein design models (e.g., ProteinMPNN) are **restricted to 20 canonical amino acids** and cannot handle NCAAs. Rosetta, being physics-based, computes energy from first principles — it doesn't need to have "seen" a residue before to score it — enabling it to model arbitrary non-canonical chemistries.

**This is Rosetta's unique advantage over ML methods**, and the core capability this benchmark evaluates.

### What Is TRF?

TRF is a derivative of tryptophan (Trp) with a **formyl group (-CHO) at the N1 position of the indole ring**. This small modification gives TRF distinct chemical properties:
- The formyl group can act as a hydrogen bond acceptor
- Alters the indole ring's electron distribution, affecting π-π stacking
- Introduces additional polarity into protein cores, challenging design quality

## Test Proteins

This task includes **3 diverse protein scaffolds** covering different fold types and sizes:

| Protein | PDB ID | Length | Fold Type | TRF Position | Design Positions |
|:--------|:------:|:------:|:----------|:------------:|:----------------:|
| Ubiquitin | 1ubq | 76 | α/β mixed | 4 | 8 |
| Protein G B1 domain | 1bdd | 56 | α/β mixed | 3 | 8 |
| Engrailed homeodomain | 1enh | 54 | All-α helix | 5 | 8 |

**Scoring**: Each protein is scored independently; scores are summed. TRF must be present at the correct position in ALL proteins for the design to be valid.

## Input

The candidate script (`scripts/init.py`) receives:

- `--prepared-input`: Path to a prepared PDB (TRF placed, params loaded)
- `--solution-output`: Path for the designed PDB output

## Output

The candidate must output a PDB file containing:
1. **Unchanged** backbone coordinates
2. **TRF retained** at the specified position
3. Optimized side chains at surrounding design positions
4. Only standard 20 AAs at non-TRF positions

## Scoring

The evaluator uses PyRosetta's `ref2015` score function with loaded TRF params:

| Metric | Description |
|:-------|:------------|
| `trf_present` | Whether TRF is correctly inserted at the target position |
| `total_energy` | Rosetta ref2015 total energy (lower = better) |
| `improvement` | native_energy - total_energy (positive = improved) |
| `combined_score` | improvement / \|native_energy\| |

`combined_score` is only valid when TRF is at the correct position; otherwise set to `-1e18`.

## Constraints

1. Only modify `scripts/init.py`
2. Do NOT modify backbone coordinates
3. TRF must be present at the specified position in ALL proteins
4. Only use standard 20 AAs at non-TRF positions
5. Output must be a valid PDB file
6. All 3 test proteins are automatically iterated by the evaluator

## Improvement Directions for Agents

1. **Iterative design cycles**: Repeated repacking to find better rotamer combinations
2. **TRF rotamer search**: Try different TRF side chain conformations, select lowest energy
3. **Monte Carlo simulated annealing**: Accept occasional energy increases to escape local minima
4. **Limited backbone flexibility**: Small backbone adjustments near the TRF site (where allowed)
5. **Cooperative site design**: Mutate multiple positions simultaneously rather than sequentially
