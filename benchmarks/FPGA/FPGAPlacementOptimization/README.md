# FPGA Placement Optimization

Optimize the placement of digital logic on an FPGA device: assign each instance
(LUT, FF, DSP, BRAM, carry chain) to a legal site to minimize wirelength while
satisfying all FPGA-specific legality constraints.

This benchmark is based on the **ISPD 2016 FPGA Placement Contest** benchmarks.

## Benchmark Philosophy

This benchmark evaluates an agent's ability to **design and iteratively improve an FPGA placement algorithm**. FPGA placement is a classical electronic-design-automation problem with real engineering constraints: a placement must be fully legal before it can be used, and wirelength directly impacts circuit timing, power, and routability.

The editable artifact (`scripts/init.py`) is intentionally a **lightweight feasible implementation**  — a naive row-scan placer that produces a legal but high-wirelength placement using only the Python standard library. This design choice serves two purposes:

- It provides a **clear baseline to improve upon** rather than asking agents to tune an already-optimized production placer.
- It keeps the **entry barrier low**: agents can focus on placement algorithm design without managing external dependencies, GPU toolchains, or proprietary frameworks.

This benchmark is **not** designed to evolve or tune an existing production FPGA placer such as aug-elfPlace or DreamPlaceFPGA. Those systems represent years of engineering effort and are better treated as reference material. Instead, the benchmark challenges agents to **design a placement strategy from a feasible starting point**, with full freedom to replace the algorithm entirely while respecting the benchmark interface.

The evaluator enforces a sharp separation between the candidate algorithm and the scoring pipeline: it runs the candidate program, checks legality, and computes HPWL — all independently of the candidate's internal implementation. This means an agent could use analytical placement, simulated annealing, constructive heuristics, or machine learning, and the evaluator would treat each equally as long as the output is legal and the wirelength is minimized.

## Agent Task

The **editable artifact** is `scripts/init.py`.

This file implements a lightweight, deterministic row-scan placer that produces
a legal but high-wirelength placement. It is intentionally simple:

- It uses **only Python standard library** — no external dependencies.
- It is **not a wrapper** around aug-elfPlace, DreamPlaceFPGA, or any production placer.
- It is a **starting point** — a feasible but suboptimal placement that the agent
  is expected to redesign and improve.

The agent has **full freedom** to redesign the placement algorithm.
The only constraints are:

1. The program must accept the same command-line interface (`--nodes`, `--pl`, `--scl`, `--output`).
2. The program must produce `solution.pl` in the same format.
3. The placement must satisfy the three legality gates (G1, G2, G3).

Everything inside the `EVOLVE-BLOCK` in `scripts/init.py` — the placement
algorithm functions — may be modified, replaced, or removed. The benchmark
parsers (.nodes, .pl, .scl), output writer, and CLI entry point are
outside the EVOLVE-BLOCK and are **frozen**.

## Baseline

The `baseline/` directory contains the same row-scan implementation as a
**reference score** for human comparison. Agents do not modify the baseline.
The evaluator never compares candidate output against the baseline; it scores
candidate output independently.

## Evaluation

The evaluator (`verification/evaluator.py`) scores a candidate by:

1. Running the candidate program (`scripts/init.py`) to produce `solution.pl`.
2. Computing **HPWL** (half-perimeter wirelength) using an independent NumPy
   implementation.
3. Checking **hard validation gates**: site-type compatibility (G1), resource
   capacity (G2), and carry-chain integrity (G3).
4. Returning `combined_score = -HPWL` for fully legal placements, or
   `combined_score = -1e18` for invalid placements.

The evaluator is **independent** from the candidate program. It does not compare
against the baseline. It scores only the candidate output.

## Datasets

This benchmark provides two tiers of evaluation data:

### Bundled: fpga-example1 (default)

The **fpga-example1** design (`references/design.*`) is bundled with the
repository. It is a lightweight benchmark (~1 MB, ~3000 instances) that serves
as the default evaluation target. This is a deliberate design choice:

- **Fast evaluation**: Frontier-Agent performs many evaluation iterations during
  evolution. A lightweight benchmark keeps iteration times under 1 second.
- **Deterministic ground truth**: The small design makes it practical to verify
  correctness and debug placement algorithms.
- **Sufficient complexity**: Despite its small size, fpga-example1 exercises all
  three legality gates (SLICE/DSP/BRAM site types, resource capacity, carry
  chains) and produces meaningful HPWL comparisons.

### Separate download: ISPD 2016 suite

The complete **ISPD 2016 benchmark suite** (12 designs: FPGA01--FPGA12, approx.
1 GB uncompressed) is **not** bundled with the repository due to its size. It
must be downloaded separately from the official contest release.

The evaluator supports these designs via the `--benchmark` flag once the dataset
is set up locally:

## Dataset Setup

### ISPD 2016 benchmark suite

1. Download the official ISPD 2016 FPGA Placement Contest benchmarks:
   [ISPD 2016 Contest benchmarks](http://www.ispd.cc/contests/16/benchmarks.html)
   (direct links are provided on the contest page for each of the 12 designs).

2. Extract each design into the `references/ispd2016/` directory so that the
   structure matches:

   ```
   references/ispd2016/
   ├── FPGA01/
   │   ├── design.nodes
   │   ├── design.nets
   │   ├── design.pl
   │   ├── design.scl
   │   ├── design.lib
   │   ├── design.lc
   │   ├── design.wts
   │   └── design.aux
   ├── FPGA02/
   ...
   └── FPGA12/
   ```

   Note: Some design files in the official release are packaged as `.tar.gz`
   archives and must be extracted before use.

3. Verify the setup by running the evaluator against one of the designs:

   ```bash
   python verification/evaluator.py scripts/init.py --benchmark FPGA01
   ```

   Expected output: a valid HPWL score with all three legality gates passing.

### Alternative: copy from DREAMPlaceFPGA / aug-elfPlace

If you have the aug-elfPlace repository available locally, its benchmark
directory (`benchmarks/ispd2016/`) contains the complete ISPD 2016 suite
already extracted. Copy the `FPGA01`--`FPGA12` directories into
`references/ispd2016/`.

```bash
python verification/evaluator.py scripts/init.py --benchmark FPGA01
```

If the requested benchmark directory is missing, the evaluator will print a
clear error message with setup instructions.

## File Structure

```
FPGAPlacementOptimization/
├── README.md                                     Navigation doc (this file)
├── Task.md                                       Core task contract
├── references/                                   Benchmark datasets (read-only)
│   ├── design.*                                  fpga-example1 (default benchmark)
│   └── ispd2016/                                 ISPD 2016 suite (separate download, see Dataset Setup)
├── baseline/                                     Reference baseline (row-scan placer)
│   ├── solution.py                               Reference implementation
│   └── result_log.txt                            Expected results
├── scripts/
│   └── init.py                                   Editable placer entry point
├── verification/
│   ├── canonical.py                              Reference parsers, HPWL, legality gates
│   ├── evaluator.py                              Frozen scoring pipeline
│   └── requirements.txt                          Dependencies (numpy)
├── frontier_eval/                                Unified-task metadata
├── ClockAwarePlacement_Design_Report.md          Design exploration (archival)
└── ClockAwarePlacement_DesignValidation.md       Design validation (archival)
```

## Quick Start

### 1. Dependencies

```bash
pip install numpy
```

### 2. Run the Initial Solver

```bash
cd benchmarks/FPGA/FPGAPlacementOptimization
python scripts/init.py
# Produces: solution.pl
# Expected: HPWL ~210721, all gates pass
```

### 3. Evaluate a Candidate

Default benchmark (fpga-example1, bundled):

```bash
python verification/evaluator.py scripts/init.py
```

Evaluate against an ISPD 2016 design (requires separate dataset download):

```bash
python verification/evaluator.py scripts/init.py --benchmark FPGA01
python verification/evaluator.py scripts/init.py --benchmark FPGA07
python verification/evaluator.py scripts/init.py --benchmark FPGA12
```

Available designs: `FPGA01` through `FPGA12`.

Output is a JSON object with `combined_score`, `hpwl`, `valid`, and per-gate results.

### 4. Run with frontier_eval (unified)

```bash
python -m frontier_eval task=unified task.benchmark=FPGA/FPGAPlacementOptimization algorithm.iterations=0
```

## Benchmarks

| Dataset | Location | Designs | Size | Use |
|---------|----------|---------|------|-----|
| fpga-example1 (default) | references/ | 1 design | ~1 MB | Fast iteration during evolution |
| ISPD 2016 | references/ispd2016/ (separate download) | 12 designs (FPGA01-FPGA12) | ~1 GB | Extended evaluation |

## References

- **ISPD 2016 FPGA Placement Contest** -- [Contest page](http://www.ispd.cc/contests/16/FAQ.html)
- **aug-elfPlace** -- Rachel Selina Rajarathnam et al., "Better Together:
  Combining Analytical and Annealing Methods for FPGA Placement," FPL 2024.
  [GitHub](https://github.com/rachelselinar/DREAMPlaceFPGA) (reference implementation)

## Design Documents

- ClockAwarePlacement_Design_Report.md -- Initial benchmark architecture design.
- ClockAwarePlacement_DesignValidation.md -- Source-code validation of design
  assumptions; documents why "clock-aware" constraints are not present in the
  baseline and why the benchmark is reformulated as pure placement optimization.





