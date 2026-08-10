#!/usr/bin/env python3
"""Row-based placement baseline for VLSI Global Placement.

This baseline matches the algorithm in scripts/init.py.
It is intentionally simple: legal but poor HPWL.
"""

import json
import sys
import time
from pathlib import Path


def _open_reference(path):
    """Open a reference file, transparently decompressing gzip data."""
    if str(path).endswith(".json.gz"):
        import gzip
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def load_benchmark(benchmark_name):
    candidates = [
        Path("references") / f"{benchmark_name}.json",
        Path("references") / f"{benchmark_name}.json.gz",
        Path(__file__).resolve().parent.parent / "references" / f"{benchmark_name}.json",
        Path(__file__).resolve().parent.parent / "references" / f"{benchmark_name}.json.gz",
    ]
    for p in candidates:
        if p.is_file():
            with _open_reference(p) as f:
                return json.load(f)
    raise FileNotFoundError(f"Benchmark {benchmark_name}.json[.gz] not found")


def compute_hpwl(placement, netlist, cells):
    total_hpwl = 0.0
    for net in netlist:
        xs = []
        ys = []
        for pin in net:
            cname = pin["cell"]
            if cname not in placement:
                continue
            cx, cy = placement[cname]
            w = cells[cname]["width"]
            h = cells[cname]["height"]
            px = cx + w / 2 + pin.get("x_offset", 0.0)
            py = cy + h / 2 + pin.get("y_offset", 0.0)
            xs.append(px)
            ys.append(py)
        if xs:
            total_hpwl += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return total_hpwl


def place_components(die, cells, fixed_cells, movable_cells, netlist, initial_placement):
    """Deterministic row-based placement."""
    die_w = die["width"]
    die_h = die["height"]
    row_h = die["row_height"]
    n_rows = int(die_h // row_h)

    placement = {}
    for c in fixed_cells:
        placement[c] = [initial_placement[c]["x"], initial_placement[c]["y"]]

    row_cursor = [0.0] * n_rows
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

    tall_cells = [c for c in movable_cells if cells[c]["height"] > row_h]
    std_cells = [c for c in movable_cells if cells[c]["height"] == row_h]

    tall_cells.sort(key=lambda c: (-cells[c]["height"], -cells[c]["width"] * cells[c]["height"], c))
    std_cells.sort(key=lambda c: (-cells[c]["width"] * cells[c]["height"], c))

    for c in tall_cells:
        cw = cells[c]["width"]
        ch = cells[c]["height"]
        rows_needed = max(1, int(ch // row_h))
        found = False
        for r in range(n_rows - rows_needed + 1):
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
            placement[c] = [0.0, 0.0]

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


def main():
    benchmark_name = sys.argv[1] if len(sys.argv) > 1 else "adaptec1"
    print("=" * 60)
    print("VLSI Global Placement - Row-based Baseline")
    print("=" * 60)
    print()
    print(f"Loading benchmark: {benchmark_name}")
    data = load_benchmark(benchmark_name)
    print(f"  Die: {data['die']['width']} x {data['die']['height']}")
    print(f"  Cells: {len(data['cells'])} total "
          f"({len(data['fixed_cells'])} fixed, {len(data['movable_cells'])} movable)")
    print(f"  Nets: {data['num_nets']}, Pins: {data['num_pins']}")
    print()

    print("Running row-based placement...")
    t0 = time.time()
    placement = place_components(
        die=data["die"],
        cells=data["cells"],
        fixed_cells=data["fixed_cells"],
        movable_cells=data["movable_cells"],
        netlist=data["netlist"],
        initial_placement=data["initial_placement"],
    )
    runtime = time.time() - t0
    hpwl = compute_hpwl(placement, data["netlist"], data["cells"])
    print(f"  Runtime: {runtime:.2f}s")
    print(f"  HPWL: {hpwl:.2f}")
    print(f"  Cells placed: {len(placement)}")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()