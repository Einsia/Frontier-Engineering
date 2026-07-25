"""
VLSI Global Placement - ISPD 2005 Benchmarks

Baseline Algorithm: Deterministic Row-Based Placement

- ALLOWED TO MODIFY: place_components()
- NOT ALLOWED TO MODIFY: load_benchmark(), compute_hpwl(), main(), output format

Strategy:
1. Fixed cells remain at their initial positions (unchanged).
2. Movable cells sorted by height descending, then area descending, then name.
3. Row cursor tracks the next available x position in each row.
4. Tall macros (height > row_height) placed first, checking all spanned rows.
5. Standard cells (height == row_height) fill remaining row space.
"""

import json
import math
import os
import sys
import time
from pathlib import Path


def _decompress_netlist(data: dict) -> dict:
    """Decompress compact netlist (cell indices) into original format (cell names + zero offsets)."""
    if not data.get("netlist") or not data["netlist"]:
        return data
    if isinstance(data["netlist"][0], list) and data["netlist"][0] and isinstance(data["netlist"][0][0], dict):
        return data
    cell_names = list(data["cells"].keys())
    new_netlist = []
    for net in data["netlist"]:
        new_net = [{"cell": cell_names[idx], "x_offset": 0.0, "y_offset": 0.0} for idx in net]
        new_netlist.append(new_net)
    data["netlist"] = new_netlist
    return data


# ============================================================================
# DATA LOADING (NOT ALLOWED TO MODIFY - Interface must match evaluator)
# ============================================================================

def load_benchmark(benchmark_name: str | None = None) -> dict:
    """Load the benchmark reference JSON. DO NOT MODIFY."""
    if benchmark_name is None:
        benchmark_name = os.environ.get("BENCHMARK_NAME", "adaptec1")

    candidates = [
        Path("references") / f"{benchmark_name}.json",
        Path(__file__).resolve().parent.parent / "references" / f"{benchmark_name}.json",
    ]
    for p in candidates:
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                return _decompress_netlist(data)
    raise FileNotFoundError(
        f"Benchmark reference JSON '{benchmark_name}.json' not found. "
        "Searched: " + ", ".join(str(c) for c in candidates)
    )


# ============================================================================
# HPWL COMPUTATION (NOT ALLOWED TO MODIFY - Must match evaluator)
# ============================================================================

def compute_hpwl(placement: dict, netlist: list, cells: dict) -> float:
    """Compute Half-Perimeter Wirelength. DO NOT MODIFY."""
    total_hpwl = 0.0
    for net in netlist:
        xs = []
        ys = []
        for pin in net:
            cell_name = pin["cell"]
            if cell_name not in placement:
                continue
            cx, cy = placement[cell_name]
            w = cells[cell_name]["width"]
            h = cells[cell_name]["height"]
            px = cx + w / 2 + pin.get("x_offset", 0.0)
            py = cy + h / 2 + pin.get("y_offset", 0.0)
            xs.append(px)
            ys.append(py)
        if xs:
            total_hpwl += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return total_hpwl


# ============================================================================
# PLACEMENT ALGORITHM (ALLOWED TO MODIFY - This is your optimization code)
# ============================================================================

# EVOLVE-BLOCK-START
def place_components(
    die: dict,
    cells: dict,
    fixed_cells: list,
    movable_cells: list,
    netlist: list,
    initial_placement: dict,
) -> dict:
    """Place all movable cells using deterministic row-based placement.

    Strategy:
    1. Fixed cells remain at their initial positions.
    2. Movable cells sorted by height descending, then area descending, then name.
    3. Row cursor tracks the next available x position in each row.
    4. Tall macros (height > row_height) placed first, checking all rows they span.
    5. Standard cells (height == row_height) fill remaining row space.
    """
    die_w = die["width"]
    die_h = die["height"]
    row_h = die["row_height"]
    n_rows = int(die_h // row_h)

    # Initialize placement with fixed cells at their initial positions
    placement = {}
    for c in fixed_cells:
        placement[c] = [initial_placement[c]["x"], initial_placement[c]["y"]]

    # Row cursor: next available x position in each row
    row_cursor = [0.0] * n_rows

    # Mark fixed cell occupancy in row cursors
    for c in fixed_cells:
        cx, cy = placement[c]
        cw = cells[c]["width"]
        ch = cells[c]["height"]
        r_start = max(0, int(cy // row_h))
        r_end = min(n_rows - 1, int((cy + ch - 1) // row_h))
        for r in range(r_start, r_end + 1):
            right = cx + cw
            if right > row_cursor[r]:
                row_cursor[r] = right

    # Separate tall macros (>1 row) and standard cells (1 row)
    tall_cells = [c for c in movable_cells if cells[c]["height"] > row_h]
    std_cells = [c for c in movable_cells if cells[c]["height"] == row_h]

    # Sort tall cells: height desc, area desc, name
    tall_cells.sort(key=lambda c: (
        -cells[c]["height"],
        -cells[c]["width"] * cells[c]["height"],
        c
    ))

    # Sort standard cells: area desc, name
    std_cells.sort(key=lambda c: (
        -cells[c]["width"] * cells[c]["height"],
        c
    ))

    # Place tall macros: they span multiple rows
    for c in tall_cells:
        cw = cells[c]["width"]
        ch = cells[c]["height"]
        rows_needed = max(1, int(ch // row_h))

        found = False
        for r in range(n_rows - rows_needed + 1):
            # Find the maximum cursor in the spanned rows
            max_c = 0.0
            for rr in range(r, r + rows_needed):
                if row_cursor[rr] > max_c:
                    max_c = row_cursor[rr]
            if max_c + cw <= die_w:
                x = max_c
                y = float(r * row_h)
                placement[c] = [x, y]
                for rr in range(r, r + rows_needed):
                    row_cursor[rr] = x + cw
                found = True
                break

        if not found:
            # Fallback (should not happen with < 100% utilization)
            placement[c] = [0.0, 0.0]

    # Place standard cells: fill rows from bottom to top
    # Maintain a pointer to the first row that still has space
    available_rows = [r for r in range(n_rows) if row_cursor[r] < die_w]
    row_ptr = 0

    for c in std_cells:
        cw = cells[c]["width"]
        found = False
        for ri in range(row_ptr, len(available_rows)):
            r = available_rows[ri]
            if row_cursor[r] + cw <= die_w:
                x = row_cursor[r]
                y = float(r * row_h)
                placement[c] = [x, y]
                row_cursor[r] = x + cw
                if row_cursor[r] >= die_w:
                    row_ptr = ri + 1
                found = True
                break
        if not found:
            placement[c] = [0.0, 0.0]

    return placement


# EVOLVE-BLOCK-END
def main():
    """Main routine. Keep output format (temp/submission.json) fixed."""
    print("=" * 60)
    print("VLSI Global Placement - ISPD 2005 Benchmark")
    print("=" * 60)

    # Load benchmark data
    benchmark_name = os.environ.get("BENCHMARK_NAME", "adaptec1")
    print(f"\nLoading benchmark: {benchmark_name}")
    t0 = time.time()
    data = load_benchmark(benchmark_name)
    print(f"  Loaded in {time.time() - t0:.2f}s")
    print(f"  Benchmark: {data['benchmark_name']}")
    print(f"  Die: {data['die']['width']} x {data['die']['height']}")
    print(f"  Cells: {len(data['cells'])} total "
          f"({len(data['fixed_cells'])} fixed, "
          f"{len(data['movable_cells'])} movable)")
    print(f"  Nets: {data['num_nets']}, Pins: {data['num_pins']}")

    # ALLOWED TO MODIFY: Placement algorithm call
    print("\nPlacing components...")
    t0 = time.time()
    placement = place_components(
        die=data["die"],
        cells=data["cells"],
        fixed_cells=data["fixed_cells"],
        movable_cells=data["movable_cells"],
        netlist=data["netlist"],
        initial_placement=data["initial_placement"],
    )
    print(f"  Placed in {time.time() - t0:.2f}s")
    print(f"  Cells placed: {len(placement)}")

    # Compute HPWL
    print("\nEvaluating placement...")
    t0 = time.time()
    hpwl_val = compute_hpwl(placement, data["netlist"], data["cells"])
    print(f"  HPWL evaluated in {time.time() - t0:.2f}s")
    print(f"  HPWL: {hpwl_val:.2f}")

    # Verify all movable cells are placed
    missing = [c for c in data["movable_cells"] if c not in placement]
    if missing:
        print(f"  WARNING: {len(missing)} movable cells not placed!")

    # NOT ALLOWED TO MODIFY: Output format must match exactly
    submission = {
        "benchmark_id": "vlsi_global_placement",
        "benchmark_name": data["benchmark_name"],
        "placement": placement,
    }

    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    submission_path = temp_dir / "submission.json"

    with open(submission_path, "w", encoding="utf-8") as f:
        json.dump(submission, f, indent=2)

    print(f"\nsubmission.json written to {submission_path}")
    print(f"  Cells placed: {len(placement)}")
    print(f"  HPWL: {hpwl_val:.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
