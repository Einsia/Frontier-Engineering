# Task: FPGA Placement Optimization

## 1. Problem

Improve the placement algorithm implemented in `scripts/init.py`. This program reads an FPGA benchmark circuit (in ISPD Bookshelf format) and assigns each logic instance (LUT, FF, DSP, BRAM) to a legal site on the FPGA grid. The goal is to **minimize half-perimeter wirelength (HPWL)** while satisfying all FPGA-specific legality constraints.

This benchmark is based on the **ISPD 2016 FPGA Placement Contest** benchmarks and the **FPGA Bookshelf format** (`.nodes`, `.nets`, `.pl`, `.scl`, `.lib`, `.lc`).

The task: **improve the placement algorithm in `scripts/init.py` to produce lower-wirelength placements.** The file contains a naive row-scan placer that produces a legal but high-wirelength placement. An improved algorithm should reduce HPWL while maintaining legality.

## 2. What the Agent May Modify

This benchmark intentionally does **not** prescribe any specific placement algorithm. The agent has full freedom to redesign the placement strategy within `scripts/init.py`.

Possible approaches include, but are not limited to:

- **Constructive placement** ！ place instances greedily using heuristics (row-scan, quadratic assignment, or partitioning-based methods).
- **Analytical placement** ！ formulate placement as a continuous optimization problem with differentiable wirelength proxies and density penalties.
- **Simulated annealing** ！ start from an initial placement and iteratively perturb and improve.
- **Reinforcement learning** ！ train a policy to place instances sequentially.
- **Integer programming** ！ formulate legality and wirelength as an exact optimization problem.
- **Hybrid approaches** ！ combine multiple strategies (e.g., analytical global placement followed by legalization).

The only requirements are:

1. The program must accept the same command-line interface (`--nodes`, `--pl`, `--scl`, `--output`).
2. The program must produce `solution.pl` in the Bookshelf format described in Section 7 (Submission Contract).
3. The placement must satisfy all three legality gates (G1, G2, G3) described in Section 6 (Constraints).

The evaluator judges **only the generated placement quality and legality**, not the internal implementation. An agent that replaces the entire placement algorithm with a completely different approach is treated identically to one that makes incremental modifications to the row-scan placer ！ both are scored solely by the resulting HPWL and legality of the output placement.

## 3. Input Format (ISPD Bookshelf for FPGA)

Benchmark designs use the **Bookshelf format** extended for FPGA placement. Each design has the following files in `references/`:

| File | Extension | Description |
|------|-----------|-------------|
| Auxiliary | `.aux` | Root file listing all other design files |
| Nodes | `.nodes` | List of instances (movable and fixed) with their master cell types |
| Nets | `.nets` | Netlist: each net connects a set of instance pins |
| Placement | `.pl` | Instance locations (x, y, z/BEL) -- input provides fixed IO locations only |
| SCL | `.scl` | Site/clock layout: site definitions, resources per site, and site map grid |
| Library | `.lib` | Cell library: pin definitions, directions (INPUT/OUTPUT), clock/control attributes |
| Weights | `.wts` | Net weights (typically all 1.0) |
| Legality Constraints | `.lc` | Architecture-specific legality constraint parameters |

The `.aux` file is the entry point:

```
design : design.nodes design.nets design.wts design.pl design.scl design.lib
```

### Nodes file

Each line: `<instance_name> <cell_type>`

```
inst_7 FDRE
inst_8 FDRE
...
inst_3340 IBUF
```

Fixed instances (IO pads, PLLs) are listed in the input `.pl` file and must not be moved.

### Nets file

Each net: `net <net_name> <degree>` followed by pin references, terminated by `endnet`:

```
net net_1 3
  inst_7 C
  inst_8 C
  inst_3340 O
endnet
```

### SCL file

Defines the FPGA grid: site types (SLICE, DSP, BRAM, IO), per-site resource capacities, and the site map layout.

### Library file

Defines each cell type: pin names, directions, clock/control attributes. Example:

```
CELL FDRE
  PIN C INPUT CLOCK
  PIN CE INPUT
  PIN D INPUT
  PIN Q OUTPUT
ENDCELL
```

## 4. Design Variables

For each **movable** instance `i`:

- **x-coordinate** -- horizontal position on the FPGA grid (integer site column index)
- **y-coordinate** -- vertical position on the FPGA grid (integer site row index)
- **z / BEL index** -- BEL (Basic Element Location) within the site (integer, e.g., 0-15 for SLICE sites)

Fixed instances (IO pads, PLLs) have predetermined (x, y, z) and must remain at their input locations.

## 5. Objective

Minimize **half-perimeter wirelength (HPWL)**:

```
HPWL = sum_{net n} (max_{i in n} x_i - min_{i in n} x_i + max_{i in n} y_i - min_{i in n} y_i)
```

HPWL is computed from the **final legal placement** using the centroid of each instance site as its position.

## 6. Constraints (Hard Validation Gates)

A placement solution must satisfy three legality gates. Any violation makes the placement invalid.

### G1: Site-Type Compatibility

Each instance must be placed on a site type compatible with its cell type:

| Cell Type | Compatible Site Type |
|-----------|---------------------|
| LUT6, LUT5, LUT4, LUT3, LUT2, LUT1 | SLICE |
| FDRE, FDCE, FDPE, LDCE | SLICE |
| CARRY4, CARRY8 | SLICE |
| DSP48E2, DSP48E1 | DSP |
| RAMB36E2, RAMB18E2, RAMB36E1, RAMB18E1 | BRAM |
| IBUF, OBUF, BUFGCE, BUFG | IO |

### G2: Resource Capacity

Each site has a maximum capacity for each resource type. For a SLICE site (simplified Ultrascale):

- **LUT capacity**: 16 per SLICE (8 per half-SLICE)
- **FF capacity**: 16 per SLICE (8 per half-SLICE)
- **DSP capacity**: 1 per DSP site
- **BRAM capacity**: 1 per BRAM site

Placement must not exceed these per-site resource limits.

### G3: Carry-Chain Integrity

Carry-chain instances (CARRY4/CARRY8) must:

- Be placed on adjacent sites in the correct order
- Maintain vertical adjacency (carry propagation direction)

## 7. Submission Contract

Your candidate program (`scripts/init.py`) must:

1. Read the benchmark input files (`.nodes`, `.nets`, `.pl`, `.scl`, `.lib`, `.lc`)
2. Compute a placement for all movable instances
3. Write a `.pl` file to the specified output path

### Output file: solution.pl

```
<instance_name> <x> <y> <z>
...
```

Example:

```
inst_7 10 15 8
inst_8 10 15 9
...
inst_3 5  3  0
```

Format rules:
- Fields are space-separated
- x and y are integer site column/row coordinates
- z is the integer BEL index within the site
- Fixed instances must appear at their original (x, y, z) from the input .pl file
- Every movable instance from .nodes must appear exactly once

## 8. Feasibility Rules

A submission is invalid (infeasible) if any of the following hold:

1. solution.pl is missing or unreadable
2. Not all movable instances from .nodes are present in solution.pl
3. Any fixed instance has been moved from its input location
4. **G1 violation**: an instance is placed on an incompatible site type
5. **G2 violation**: a site exceeds its resource capacity
6. **G3 violation**: carry-chain instances violate ordering/adjacency rules
7. Any position field (x, y, z) is non-integer, negative, or out of the device grid bounds
8. The solution.pl file contains additional undefined instances beyond what .nodes declares

## 9. Evaluation Workflow

The evaluator (`verification/evaluator.py`):

1. Runs `python scripts/init.py` to produce `solution.pl`
2. Parses the input benchmark files (.nodes, .nets, .pl, .scl)
3. Validates solution.pl completeness and format
4. Checks all three legality gates (G1, G2, G3)
5. Computes HPWL using an independent NumPy implementation
6. Returns metrics and combined score

Run from the repository root:

```bash
python benchmarks/FPGA/FPGAPlacementOptimization/verification/evaluator.py benchmarks/FPGA/FPGAPlacementOptimization/scripts/init.py
```

Or from the benchmark directory:

```bash
cd benchmarks/FPGA/FPGAPlacementOptimization
python verification/evaluator.py scripts/init.py
```

## 10. Scoring

- **Legal placement (all gates pass)**: combined_score = -HPWL

  HPWL is the raw half-perimeter wirelength summed across all nets. Lower HPWL is better; the negation in combined_score ensures a higher value is better.

- **Invalid placement (any gate fails or feasibility rule violated)**: combined_score = -1e18, valid = 0

## 11. References

- **ISPD 2016 FPGA Placement Contest**: http://www.ispd.cc/contests/16/FAQ.html
- **aug-elfPlace**: Rachel Selina Rajarathnam et al., "Better Together: Combining Analytical and Annealing Methods for FPGA Placement," FPL 2024. [GitHub](https://github.com/rachelselinar/DREAMPlaceFPGA) (reference implementation available at the repository root `baseline/aug-elfPlace/`).

- **ISPD 2016 Benchmark Format**: `references/README` describes the FPGA Bookshelf format extensions.
- **Benchmark data**: references/ (fpga-example1)

## 12. Quick Start

```bash
# From the benchmark directory:
cd benchmarks/FPGA/FPGAPlacementOptimization

# Run the initial solver:
python scripts/init.py

# Evaluate the result:
python verification/evaluator.py scripts/init.py

# Expected output: HPWL ~210721, all gates pass
```




