"""FPGA Placement Optimization - Initial Solver.

Pipeline
--------
1. Read benchmark  - Parse .nodes, .pl (fixed instances), .scl (site layout)
                     from paths provided via command-line arguments.
2. Place           - Assign every movable instance to a legal (x, y, z) site.
                     The current strategy is a naive row-scan: iterate
                     SLICE/DSP/BRAM sites in order, place instances up to
                     per-site capacity.  This guarantees legality by
                     construction, but produces high wirelength.
3. Write output    - Write solution.pl in Bookshelf format.

The evaluator runs this program, then scores solution.pl independently.

The agent is expected to evolve the placement strategy (step 2).
All benchmark I/O contracts (steps 1 and 3) should remain unchanged.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any


# ============================================================================
# READ-ONLY: Benchmark Parsing  (frozen -- do not modify)
# ============================================================================

def parse_nodes(path: str) -> list[tuple[str, str]]:
    """Parse .nodes file. Returns list of (instance_name, cell_type)."""
    instances: list[tuple[str, str]] = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                instances.append((parts[0], parts[1]))
    return instances


def parse_pl(path: str) -> dict[str, tuple[int, int, int]]:
    """Parse .pl file. Returns dict: name -> (x, y, z)."""
    placements: dict[str, tuple[int, int, int]] = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 4:
                name, x_str, y_str, z_str = parts[0], parts[1], parts[2], parts[3]
                placements[name] = (int(float(x_str)), int(float(y_str)), int(float(z_str)))
    return placements


def parse_scl(path: str) -> dict[str, Any]:
    """Parse .scl file. Returns dict with site map, capacities, resource mapping."""
    result: dict[str, Any] = {
        "site_capacities": {},
        "resources": {},
        "site_map": {},
        "num_cols": 0,
        "num_rows": 0,
    }
    current_site = None
    in_sitemap = False

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("SITE "):
                current_site = line.split(None, 1)[1]
                result["site_capacities"][current_site] = {}
            elif current_site and line.upper() == "END SITE":
                current_site = None
            elif current_site and " " in line:
                parts = line.split()
                if len(parts) >= 2 and parts[0].isalpha():
                    cap = int(parts[1]) if parts[1].isdigit() else 1
                    result["site_capacities"][current_site][parts[0]] = cap

            elif line.startswith("SITEMAP"):
                parts = line.split()
                if len(parts) >= 3:
                    result["num_cols"] = int(parts[1])
                    result["num_rows"] = int(parts[2])
                in_sitemap = True
            elif line == "END SITEMAP":
                in_sitemap = False
            elif in_sitemap:
                parts = line.split()
                if len(parts) >= 3:
                    col, row, stype = int(parts[0]), int(parts[1]), parts[2]
                    result["site_map"][(col, row)] = stype

    result["cell_to_site"] = {
        "LUT1": "SLICE", "LUT2": "SLICE", "LUT3": "SLICE",
        "LUT4": "SLICE", "LUT5": "SLICE", "LUT6": "SLICE",
        "FDRE": "SLICE",
        "CARRY4": "SLICE", "CARRY8": "SLICE",
        "DSP48E1": "DSP", "DSP48E2": "DSP",
        "RAMB18E1": "BRAM", "RAMB18E2": "BRAM",
        "RAMB36E1": "BRAM", "RAMB36E2": "BRAM",
        "IBUF": "IO", "OBUF": "IO", "BUFGCE": "IO",
    }
    return result


# ============================================================================
# EVOLVE-BLOCK-START
# The agent may redesign or replace everything below this line.
# ============================================================================

def is_slice_cell(cell_type: str) -> bool:
    """Check if a cell type belongs to a SLICE site."""
    return (cell_type.startswith("LUT") or cell_type in ("FDRE",)
            or cell_type.startswith("CARRY"))


def get_site_type(cell_type: str, cell_to_site: dict[str, str]) -> str | None:
    """Return the site type required for a given cell type."""
    return cell_to_site.get(cell_type)


def row_scan_place(
    instances: list[tuple[str, str]],
    fixed_pl: dict[str, tuple[int, int, int]],
    scl_data: dict[str, Any],
) -> dict[str, tuple[int, int, int]]:
    """Naive row-scan placement: assign each movable instance to the first
    available legal site.  Guarantees legality by construction.

    Parameters
    ----------
    instances : list of (name, cell_type) from .nodes
    fixed_pl : dict of fixed placements from .pl
    scl_data : parsed .scl data

    Returns
    -------
    placements : dict name -> (x, y, z)
    """
    placements: dict[str, tuple[int, int, int]] = {}
    capacities = scl_data["site_capacities"]
    site_map = scl_data["site_map"]
    cell_to_site = scl_data["cell_to_site"]

    # Collect fixed placements
    for name, (x, y, z) in fixed_pl.items():
        placements[name] = (x, y, z)

    # Group movable instances by required site type
    groups: dict[str, list[tuple[str, str]]] = {}
    for name, ctype in instances:
        if name in placements:
            continue  # already fixed
        stype = get_site_type(ctype, cell_to_site)
        if stype is None:
            continue
        if stype not in groups:
            groups[stype] = []
        groups[stype].append((name, ctype))

    # Collect sites of each type (sorted by column, then row for deterministic order)
    sites_by_type: dict[str, list[tuple[int, int]]] = {}
    for (col, row), stype in sorted(site_map.items()):
        if stype not in sites_by_type:
            sites_by_type[stype] = []
        sites_by_type[stype].append((col, row))

    # Per-site usage tracker
    site_usage: dict[tuple[int, int], dict[str, int]] = {}

    def get_usage(site_key: tuple[int, int]) -> dict[str, int]:
        if site_key not in site_usage:
            site_usage[site_key] = {"LUT": 0, "FF": 0}
        return site_usage[site_key]

    slc_cap = capacities.get("SLICE", {})
    max_lut_per_slice = slc_cap.get("LUT", 16)
    max_ff_per_slice = slc_cap.get("FF", 16)

    # Place SLICE instances (LUTs and FFs) with capacity tracking
    slice_instances = groups.get("SLICE", [])
    slice_sites = sites_by_type.get("SLICE", [])
    site_idx = 0
    bel_idx = 0

    # Separate LUT and FF instances for capacity-aware placement
    luts = [(n, t) for n, t in slice_instances if t.startswith("LUT")]
    ffs = [(n, t) for n, t in slice_instances if t == "FDRE"]

    def place_group(
        group: list[tuple[str, str]],
        sites: list[tuple[int, int]],
        max_per_site: int,
        usage_key: str,
    ) -> None:
        nonlocal site_idx, bel_idx
        site_idx = 0
        bel_idx = 0
        for name, ctype in group:
            while site_idx < len(sites):
                site = sites[site_idx]
                usage = get_usage(site)
                if usage[usage_key] < max_per_site:
                    usage[usage_key] += 1
                    z = usage[usage_key] - 1
                    placements[name] = (site[0], site[1], z)
                    bel_idx += 1
                    break
                site_idx += 1
                bel_idx = 0

    # Place LUTs first, then FFs (they share the same SLICE sites)
    site_idx = 0
    place_group(luts, slice_sites, max_lut_per_slice, "LUT")
    site_idx = 0
    place_group(ffs, slice_sites, max_ff_per_slice, "FF")

    # Place DSP instances (1 per DSP site)
    dsp_instances = groups.get("DSP", [])
    dsp_sites = sites_by_type.get("DSP", [])
    for i, (name, ctype) in enumerate(dsp_instances):
        if i < len(dsp_sites):
            placements[name] = (dsp_sites[i][0], dsp_sites[i][1], 0)

    # Place BRAM instances (1 per BRAM site)
    bram_instances = groups.get("BRAM", [])
    bram_sites = sites_by_type.get("BRAM", [])
    for i, (name, ctype) in enumerate(bram_instances):
        if i < len(bram_sites):
            placements[name] = (bram_sites[i][0], bram_sites[i][1], 0)

    return placements


# ============================================================================
# EVOLVE-BLOCK-END
# The agent must NOT modify anything below this line.
# ============================================================================


# ============================================================================
# READ-ONLY: Output Writer and CLI Entry Point (frozen -- do not modify)
# ============================================================================

def write_pl(placements: dict[str, tuple[int, int, int]], output_path: str) -> None:
    """Write placements to a .pl file in Bookshelf format."""
    with open(output_path, "w") as f:
        for name in sorted(placements.keys()):
            x, y, z = placements[name]
            f.write(f"{name} {x} {y} {z}\n")
    print(f"Placement written to {output_path}: {len(placements)} instances")


def main() -> None:
    parser = argparse.ArgumentParser(description="FPGA Placement Optimization -- initial solver")
    parser.add_argument("--nodes", default=None, help="Path to .nodes file")
    parser.add_argument("--pl", default=None, help="Path to input .pl file (fixed instances)")
    parser.add_argument("--scl", default=None, help="Path to .scl file")
    parser.add_argument("--output", default="solution.pl", help="Output .pl file path")
    parser.add_argument("--aux", default=None, help="Path to .aux file (alternative to individual args)")
    args = parser.parse_args()

    # Resolve input paths
    ref_dir = Path(__file__).resolve().parent.parent / "references"

    if args.aux:
        aux_dir = Path(args.aux).resolve().parent
        nodes_path = aux_dir / "design.nodes"
        pl_path = aux_dir / "design.pl"
        scl_path = aux_dir / "design.scl"
    else:
        nodes_path = Path(args.nodes) if args.nodes else ref_dir / "design.nodes"
        pl_path = Path(args.pl) if args.pl else ref_dir / "design.pl"
        scl_path = Path(args.scl) if args.scl else ref_dir / "design.scl"

    if not nodes_path.is_file():
        # Fall back to references/
        nodes_path = ref_dir / "design.nodes"
        pl_path = ref_dir / "design.pl"
        scl_path = ref_dir / "design.scl"

    print(f"Nodes: {nodes_path}")
    print(f"PL:    {pl_path}")
    print(f"SCL:   {scl_path}")

    # Parse
    instances = parse_nodes(str(nodes_path))
    fixed_pl = parse_pl(str(pl_path))
    scl_data = parse_scl(str(scl_path))

    print(f"Instances: {len(instances)} total, {len(fixed_pl)} fixed, {len(instances) - len(fixed_pl)} movable")

    # Place
    placements = row_scan_place(instances, fixed_pl, scl_data)

    # Write output
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_pl(placements, str(output_path))

    # Verify all instances placed
    missing = [n for n, _ in instances if n not in placements]
    if missing:
        print(f"WARNING: {len(missing)} instances were not placed!", file=sys.stderr)


if __name__ == "__main__":
    main()
