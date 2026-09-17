# VLSI Global Placement

Global placement is a critical stage in VLSI (Very Large Scale Integration) physical design.
After logic synthesis and floorplanning, standard cells and macros must be placed on the chip
such that wirelength is minimized while respecting physical constraints.

This benchmark uses the **ISPD 2005** placement contest benchmarks, the industry-standard
open-source benchmark suite for VLSI placement. The agent must implement a placement algorithm
that minimizes Half-Perimeter Wirelength (HPWL) without violating hard constraints.

## File Structure

```text
VLSIGlobalPlacement/
├── .gitignore                        # Git ignore rules
├── datasets/                         # Raw ISPD 2005 Bookshelf data
│   └── ispd2005/                     # (empty; preprocessed JSONs are in references/)
├── README.md                         # Navigation doc (this file)
├── README_zh-CN.md                   # Navigation doc (Chinese)
├── Task.md                           # Detailed task description
├── Task_zh-CN.md                     # Detailed task description (Chinese)
├── references/                       # Benchmark reference data
│   ├── adaptec1.json.gz                 # Easy benchmark (~211k cells, gzip)
│   ├── adaptec1_difficulty.json       # Difficulty metadata
│   ├── adaptec3.json.gz                 # Medium benchmark (~451k cells, gzip)
│   └── adaptec3_difficulty.json       # Difficulty metadata
├── scripts/
│   ├── init.py                        # [MODIFIABLE] Placement algorithm
│   └── preprocess.py                  # Bookshelf -> JSON converter
├── verification/
│   ├── evaluator.py                   # Scoring and legality checks
┬   ├── test_evaluator.py             # Unit tests
│   ├── requirements.txt               # Python dependencies
│   └── docker/
│       └── Dockerfile                 # Containerized evaluation
├── baseline/
│   └── solution.py                    # Row-based placement baseline
┬   └── result_log.txt                 # Baseline evaluation results
└── frontier_eval/                     # Unified task metadata
    ├── initial_program.txt
    ├── eval_command.txt
    ├── agent_files.txt
    ├── artifact_files.txt
    ├── readonly_files.txt
    ├── copy_files.txt
    ├── candidate_destination.txt
    ├── eval_cwd.txt
    ├── constraints.txt
    └── run_eval.py
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r verification/requirements.txt
```

### 2. Run the Baseline Solver

```bash
cd benchmarks/ElectronicDesignAutomation/VLSIGlobalPlacement
python scripts/init.py
# Outputs: temp/submission.json
```

### 3. Evaluate a Candidate Program

```bash
cd benchmarks/ElectronicDesignAutomation/VLSIGlobalPlacement
python verification/evaluator.py scripts/init.py --benchmark adaptec1
```

### 4. Run with Unified Task Framework

```bash
python -m frontier_eval   task=unified   task.benchmark=ElectronicDesignAutomation/VLSIGlobalPlacement   algorithm=openevolve   algorithm.iterations=0
```

## Benchmarks

| Name | Difficulty | Fixed Cells | Movable Cells | Nets | Pins | Die Size |
|------|-----------|-------------|---------------|------|------|----------|
| adaptec1 | Easy | 543 | 210,904 | 221,142 | 944,053 | 11589x11589 |
| adaptec3 | Medium | 723 | 450,927 | 466,758 | 1,875,039 | 23190x23386 |

## Task Summary

- **Input**: Die dimensions, cell library, fixed/movable cells, netlist, initial placement
- **Output**: (x, y) coordinates for every movable cell
- **Hard Constraints**: No fixed cells moved, no cells out of bounds, no overlaps
- **Optimization Objective**: Minimize Half-Perimeter Wirelength (HPWL)
- **Editable File**: scripts/init.py (only place_components() function)

## Dataset License

The ISPD 2005 benchmarks were created by the ICCAD 2005 / ISPD 2006 placement contest committees
and are freely available for academic use.

## Compressed JSON Format

The reference files are gzip-compressed JSON with a compact netlist representation.
Each net is stored as a list of integer cell indices rather than full pin dictionaries:

```json
{"netlist": [[0, 1, 2], [3, 4], ...]}
```

The compact netlist reduces JSON size by approximately 65% compared to the verbose
format, and gzip further reduces the on-disk size by about 84% (adaptec1: 22.6MB ->
3.7MB, adaptec3: 48.2MB -> 7.9MB). The `_decompress_netlist()` function in
scripts/init.py and verification/evaluator.py reconstructs the full pin
dictionaries at load time. The transformation is lossless with respect to the
HPWL computation. The scripts/preprocess.py script generates this compressed
format directly from the original Bookshelf data.

