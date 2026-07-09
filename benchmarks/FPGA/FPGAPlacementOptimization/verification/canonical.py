"""Canonical reference implementations for FPGA Placement Optimization.

This module provides the independent evaluator functions used by the
verification pipeline. All functions are pure Python + NumPy.

Functions:
    parse_nodes, parse_nets, parse_pl, parse_scl
    compute_hpwl_canonical
    check_site_type_compatibility
    check_site_capacity
    check_carry_chain_integrity
"""

from __future__ import annotations

import numpy as np
from pathlib import Path
from typing import Any


# ??????????????????????????????????????????????????????????????????????
# PARSERS
# ??????????????????????????????????????????????????????????????????????

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


def parse_nets(path: str) -> list[dict[str, Any]]:
    """Parse .nets file. Returns list of net dicts with name and pin list."""
    nets: list[dict[str, Any]] = []
    current_net: dict[str, Any] | None = None
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("net "):
                parts = line.split()
                net_name = parts[1] if len(parts) > 1 else ""
                current_net = {"name": net_name, "pins": []}
            elif line == "endnet" and current_net is not None:
                nets.append(current_net)
                current_net = None
            elif current_net is not None and " " in line:
                pin_parts = line.split()
                if len(pin_parts) >= 1:
                    current_net["pins"].append(pin_parts[0])
    return nets


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
                name = parts[0]
                x, y, z = int(float(parts[1])), int(float(parts[2])), int(float(parts[3]))
                placements[name] = (x, y, z)
    return placements


def parse_scl(path: str) -> dict[str, Any]:
    """Parse .scl file. Returns dict with site info."""
    result: dict[str, Any] = {
        "site_capacities": {},
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
        "FDRE": "SLICE", "FDCE": "SLICE", "FDPE": "SLICE", "LDCE": "SLICE",
        "CARRY4": "SLICE", "CARRY8": "SLICE",
        "DSP48E1": "DSP", "DSP48E2": "DSP",
        "RAMB18E1": "BRAM", "RAMB18E2": "BRAM",
        "RAMB36E1": "BRAM", "RAMB36E2": "BRAM",
        "IBUF": "IO", "OBUF": "IO", "BUFGCE": "IO",
    }
    return result


def is_slice_cell(cell_type: str) -> bool:
    return (cell_type.startswith("LUT") or cell_type in ("FDRE", "FDCE", "FDPE", "LDCE")
            or cell_type.startswith("CARRY"))


def get_site_type(cell_type: str, cell_to_site: dict[str, str]) -> str:
    if is_slice_cell(cell_type):
        return "SLICE"
    return cell_to_site.get(cell_type, "SLICE")


# ??????????????????????????????????????????????????????????????????????
# HPWL COMPUTATION
# ??????????????????????????????????????????????????????????????????????

def compute_hpwl_canonical(
    placements: dict[str, tuple[int, int, int]],
    netlist: list[dict[str, Any]],
) -> float:
    """Compute half-perimeter wirelength using pure NumPy.

    For each net, HPWL = (max_x - min_x) + (max_y - min_y)
    where x, y are site coordinates of each instance in the net.

    Returns total HPWL across all nets.
    """
    total_hpwl = 0.0
    for net in netlist:
        pin_instances = net["pins"]
        xs: list[float] = []
        ys: list[float] = []
        for inst_name in pin_instances:
            if inst_name in placements:
                x, y, _ = placements[inst_name]
                xs.append(float(x))
                ys.append(float(y))
        if xs:
            hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
            total_hpwl += hpwl
    return total_hpwl


# ??????????????????????????????????????????????????????????????????????
# LEGALITY GATES
# ??????????????????????????????????????????????????????????????????????

def check_site_type_compatibility(
    placements: dict[str, tuple[int, int, int]],
    instances: list[tuple[str, str]],
    scl_data: dict[str, Any],
) -> tuple[bool, list[str]]:
    """G1: Verify each instance is placed on a compatible site type.

    Returns (passes, list_of_violations).
    """
    site_map = scl_data["site_map"]
    cell_to_site = scl_data["cell_to_site"]
    violations: list[str] = []

    name_to_type = {name: ctype for name, ctype in instances}

    for name, (x, y, z) in placements.items():
        if name not in name_to_type:
            continue
        cell_type = name_to_type[name]
        required_site = get_site_type(cell_type, cell_to_site)
        actual_site = site_map.get((x, y))
        if actual_site is None:
            violations.append(f"{name} at ({x},{y}): no site exists at that location")
        elif actual_site != required_site:
            violations.append(
                f"{name} (type={cell_type}) at ({x},{y}): "
                f"requires {required_site} site, found {actual_site}"
            )

    return len(violations) == 0, violations


def check_site_capacity(
    placements: dict[str, tuple[int, int, int]],
    instances: list[tuple[str, str]],
    scl_data: dict[str, Any],
) -> tuple[bool, list[str]]:
    """G2: Verify each site does not exceed its resource capacity.

    For SLICE sites: LUT count and FF count must not exceed capacity.
    For DSP sites: at most 1 DSP instance.
    For BRAM sites: at most 1 BRAM instance.

    Returns (passes, list_of_violations).
    """
    capacities = scl_data["site_capacities"]
    slc_cap = capacities.get("SLICE", {})
    max_lut = slc_cap.get("LUT", 16)
    max_ff = slc_cap.get("FF", 16)
    violations: list[str] = []

    name_to_type = {name: ctype for name, ctype in instances}

    # Per-site resource usage
    site_usage: dict[tuple[int, int], dict[str, int]] = {}

    for name, (x, y, z) in placements.items():
        if name not in name_to_type:
            continue
        cell_type = name_to_type[name]
        site_key = (x, y)
        if site_key not in site_usage:
            site_usage[site_key] = {"LUT": 0, "FF": 0, "DSP": 0, "BRAM": 0}

        if cell_type.startswith("LUT"):
            site_usage[site_key]["LUT"] += 1
        elif cell_type in ("FDRE", "FDCE", "FDPE", "LDCE"):
            site_usage[site_key]["FF"] += 1
        elif cell_type.startswith("DSP"):
            site_usage[site_key]["DSP"] += 1
        elif cell_type.startswith("RAMB"):
            site_usage[site_key]["BRAM"] += 1

    for site_key, usage in site_usage.items():
        if usage["LUT"] > max_lut:
            violations.append(
                f"Site ({site_key[0]},{site_key[1]}): {usage['LUT']} LUTs exceeds capacity {max_lut}"
            )
        if usage["FF"] > max_ff:
            violations.append(
                f"Site ({site_key[0]},{site_key[1]}): {usage['FF']} FFs exceeds capacity {max_ff}"
            )
        if usage["DSP"] > 1:
            violations.append(
                f"Site ({site_key[0]},{site_key[1]}): {usage['DSP']} DSPs exceeds capacity 1"
            )
        if usage["BRAM"] > 1:
            violations.append(
                f"Site ({site_key[0]},{site_key[1]}): {usage['BRAM']} BRAMs exceeds capacity 1"
            )

    return len(violations) == 0, violations


def check_carry_chain_integrity(
    placements: dict[str, tuple[int, int, int]],
    instances: list[tuple[str, str]],
) -> tuple[bool, list[str]]:
    """G3: Verify carry-chain instances (CARRY4/CARRY8) maintain adjacency.

    This is a simplified check: CARRY instances placed in a column must be
    vertically adjacent in the correct order (by name suffix or position).

    Returns (passes, list_of_violations).
    """
    violations: list[str] = []

    # Find all carry chain instances
    carry_names: list[str] = []
    for name, ctype in instances:
        if ctype.startswith("CARRY") and name in placements:
            carry_names.append(name)

    if not carry_names:
        return True, []

    # Sort by name for deterministic ordering
    carry_sorted = sorted(carry_names)
    prev_x, prev_y = None, None
    for name in carry_sorted:
        x, y, z = placements[name]
        if prev_x is not None:
            if x != prev_x:
                violations.append(
                    f"Carry chain broken: {name} at col {x}, previous at col {prev_x}"
                )
            if y != prev_y + 1:
                violations.append(
                    f"Carry chain gap: {name} at row {y}, expected row {prev_y + 1}"
                )
        prev_x, prev_y = x, y

    return len(violations) == 0, violations
