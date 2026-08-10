# VLSI Global Placement

## 1. Engineering Background

VLSI Global Placement is a critical stage in the ASIC physical design flow.
After logic synthesis converts RTL to a gate-level netlist, and floorplanning
defines the chip outline and macro positions, global placement assigns
approximate locations to all standard cells.

The complete industrial flow is:

```
RTL → Synthesis → Floorplanning → Global Placement → Detailed Placement
→ Clock Tree Synthesis → Routing → Timing Signoff → Physical Verification
```

Global placement is the first step where interconnect wirelength becomes
visible. It produces a **rough but legal** placement that a detailed placer
then refines. The quality of global placement directly affects:

- **Routing congestion**: Poor placement creates routing hotspots
- **Timing**: Longer wires increase RC delay
- **Power**: Longer wires increase dynamic power consumption
- **Area**: Inefficient placement may require larger die area

Modern industrial placers (Cadence Innovus, Synopsys ICC2, OpenROAD) all
include a global placement phase that optimizes HPWL while maintaining
density constraints.

## 2. Problem Definition

### Input

The benchmark provides the following data in JSON format:

| Field | Type | Description |
|-------|------|-------------|
| benchmark_name | string | Benchmark identifier |
| die | dict | Die dimensions: {width, height, row_height, min_x, min_y} |
| cells | dict | Cell library: {cell_name: {width, height}} |
| fixed_cells | list[str] | Names of fixed (terminal) cells |
| movable_cells | list[str] | Names of movable (standard) cells |
| initial_placement | dict | Initial positions: {cell_name: {x, y, orientation}} |
| netlist | list[list[dict]] | Nets: [[{cell, x_offset, y_offset}, ...], ...] |
| num_nets | int | Total number of nets |
| num_pins | int | Total number of pins |

### Output

The placement algorithm must produce a dictionary mapping each movable
cell name to its [x, y] coordinates:

```json
{
  "cell_name_1": [x_coordinate, y_coordinate],
  "cell_name_2": [x_coordinate, y_coordinate],
  ...
}
```

Fixed cells must remain at their initial positions.

### Hard Constraints

The evaluator enforces three hard constraints:

1. **Fixed cells must not be moved**: Any fixed cell whose position
   differs from its initial position by more than 1e-6 invalidates the placement.

2. **All cells must be within the die boundary**: Every cell must satisfy
    <= x <= die_width - cell_width and  <= y <= die_height - cell_height.

3. **No overlapping cells**: For any pair of cells, the overlap area
   must be zero. The evaluator checks axis-aligned bounding box intersection.

Violating any hard constraint sets valid = 0 and combined_score = -1e18.

### Optimization Objective

**Minimize Half-Perimeter Wirelength (HPWL)**.

For each net, HPWL is defined as:

```
HPWL(net) = (max(x_pins) - min(x_pins)) + (max(y_pins) - min(y_pins))
```

Total HPWL = sum of HPWL over all nets.

The pin position is computed as:

```
pin_x = cell_x + cell_width / 2 + x_offset
pin_y = cell_y + cell_height / 2 + y_offset
```

Lower HPWL indicates a better placement. The combined score is -HPWL
for valid placements, so higher combined_score = better.

## 3. Why HPWL?

HPWL is the standard optimization objective in VLSI placement because:

- It is **deterministic** and easy to compute
- It is **strongly correlated** with routed wirelength
- It is a **proxy for timing**, power, and congestion
- It is used by **all major placement contests** (ISPD, ICCAD, DAC)
- It is the objective optimized by **all major open-source placers**
  (RePlAce, ePlace, NTUPlace3, DREAMPlace, OpenROAD)

## 4. Baseline

The provided baseline uses **deterministic row-based placement**:

- Fixed cells remain at their initial positions
- Movable cells are sorted by height (descending), then area (descending), then name
- Tall macros (height > row_height) are placed first, spanning multiple rows
- Standard cells (height == row_height) fill remaining row space from left to right
- The placement is deterministic and always produces a legal placement
- HPWL is intentionally poor, providing substantial room for agent improvement

## 5. Datasets

Two benchmarks from the ISPD 2005 placement contest suite:

| Benchmark | Difficulty | Movable Cells | Nets | Pins | Die (um) |
|-----------|-----------|--------------|------|------|----------|
| adaptec1 | Easy | 210,904 | 221,142 | 944,053 | 11589x11589 |
| adaptec3 | Medium | 450,927 | 466,758 | 1,875,039 | 23190x23386 |

The original Bookshelf-format data (datasets/ispd2005/) is not redistributed.
Preprocessed compressed JSON files (gzip + compact netlist) are in
references/. The preprocessing script scripts/preprocess.py shows how
Bookshelf format is converted to the compressed JSON format.

## 6. Evaluation

The evaluator (verification/evaluator.py):

1. Runs the candidate program in a clean subprocess with timeout
2. Reads `temp/submission.json` from the candidate
3. Checks hard constraints (fixed cells, bounds, overlap)
4. Computes HPWL
5. Returns metrics: combined_score, valid, hpwl, 
runtime_s

### Command

```bash
python verification/evaluator.py scripts/init.py --benchmark adaptec1
```

### Metrics

| Metric | Description |
|--------|-------------|
| hpwl | Total Half-Perimeter Wirelength |
| valid | 1.0 if all hard constraints satisfied, else 0.0 |
| combined_score | -hpwl if valid, -1e18 if invalid |
| runtime_s | Total evaluation runtime in seconds |
| n_cells_placed | Number of cells in placement output |
| n_fixed_moved | Number of fixed cells that were moved |
| n_out_of_bounds | Number of cells outside die boundary |
| n_overlaps | Number of overlapping cell pairs |

## 7. References

- ISPD 2005 Placement Contest: https://www.ispd.cc/contests/05/ispd05.html
- ICCAD 2005 Mixed-Size Placement Contest: https://www.sigda.org/programs/placement-contest/
- DREAMPlace: https://github.com/limbo018/DREAMPlace
- RePlAce: https://github.com/The-OpenROAD-Project/RePlAce
- ePlace: https://github.com/limbo018/ePlace
- OpenROAD: https://github.com/The-OpenROAD-Project/OpenROAD
