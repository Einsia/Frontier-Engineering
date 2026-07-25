"""Evaluator for VLSI Global Placement  - ISPD 2005 Benchmarks"""



from __future__ import annotations



import json

import math

import os

import shutil

import subprocess

import sys

import tempfile

import time

from pathlib import Path

from typing import Any


def _decompress_netlist(data: dict) -> dict:
    """Decompress compact netlist (cell indices) into original format."""
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


INVALID_COMBINED_SCORE = -1e18





# ============================================================================

# Repository root detection

# ============================================================================



def _find_repo_root(start: Path | None = None) -> Path:

    """Locate the repository root directory."""

    if "FRONTIER_ENGINEERING_ROOT" in os.environ:

        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()

    here = (start or Path(__file__)).resolve()

    for parent in [here, *here.parents]:

        if (parent / "frontier_eval").is_dir() and (parent / "benchmarks").is_dir():

            return parent

        if (parent / "frontier_eval").is_dir() and (parent / "verification").is_dir():

            return parent.parent.parent.parent

    return here.parent.parent.parent





def _tail(text: str, limit: int = 8000) -> str:

    return text if len(text) <= limit else text[-limit:]





def _truncate_middle(text: str, limit: int = 200_000) -> str:

    if len(text) <= limit:

        return text

    keep = max(0, (limit - 128) // 2)

    omitted = len(text) - 2 * keep

    return text[:keep] + f"\n\n[... truncated {omitted} chars ...]\n\n" + text[-keep:]





# ============================================================================

# Benchmark data loading

# ============================================================================



def _get_benchmark_dir(repo_root: Path) -> Path:

    return (

        repo_root

        / "benchmarks"

        / "ElectronicDesignAutomation"

        / "VLSIGlobalPlacement"

    )





def _get_reference_path(repo_root: Path, benchmark_name: str) -> Path:

    return _get_benchmark_dir(repo_root) / "references" / f"{benchmark_name}.json"





def _get_difficulty_path(repo_root: Path, benchmark_name: str) -> Path:

    return _get_benchmark_dir(repo_root) / "references" / f"{benchmark_name}_difficulty.json"





def _list_available_benchmarks(repo_root: Path) -> list[dict]:

    """List all available benchmarks with their difficulty levels."""

    ref_dir = _get_benchmark_dir(repo_root) / "references"

    results = []

    for f in sorted(ref_dir.glob("*_difficulty.json")):

        name = f.name.replace("_difficulty.json", "")

        with open(f, "r") as fh:

            meta = json.load(fh)

        results.append({"name": name, "difficulty": meta.get("difficulty", "Unknown")})

    return results





# ============================================================================

# HPWL Computation (independent implementation)

# ============================================================================



def compute_hpwl(placement: dict, netlist: list, cells: dict) -> float:

    """Compute Half-Perimeter Wirelength for the placement."""

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

# Legality checks

# ============================================================================



class LegalityResult:

    def __init__(self):

        self.valid = True

        self.errors: list[str] = []

        self.moved_fixed: list[str] = []

        self.missing: list[str] = []
        self.out_of_bounds: list[str] = []

        self.overlapping_pairs: list[tuple[str, str, float]] = []





def check_legality(

    placement: dict,

    cells: dict,

    die: dict,

    fixed_cells: list,

    movable_cells: list,

    initial_placement: dict,

) -> LegalityResult:

    """Check placement legality: fixed cells, bounds, overlap."""

    result = LegalityResult()



    die_w = die["width"]

    die_h = die["height"]



    # 1. Check all expected cells are present in placement

    all_expected = fixed_cells + movable_cells

    for c in all_expected:

        if c not in placement:

            result.errors.append(f"Cell {c} missing from placement")

            result.missing.append(c)

            result.valid = False



    # 2. Check fixed cells are not moved

    for c in fixed_cells:

        if c not in placement:

            result.errors.append(f"Fixed cell {c} missing from placement")

            result.valid = False

            continue

        ip = initial_placement.get(c, {"x": 0.0, "y": 0.0})

        px, py = placement[c]

        if abs(px - ip["x"]) > 1e-6 or abs(py - ip["y"]) > 1e-6:

            result.moved_fixed.append(c)

            result.valid = False



    # 3. Check all cells within die boundary

    for c, (px, py) in placement.items():

        if c not in cells:

            continue

        cw = cells[c]["width"]

        ch = cells[c]["height"]

        if px < 0 or py < 0 or px + cw > die_w or py + ch > die_h:

            result.out_of_bounds.append(c)

            result.valid = False



    # 4. Overlap check using spatial hashing

    # Build a grid hash for efficient overlap detection

    all_placed_cells = list(placement.keys())

    if len(all_placed_cells) > 0:

        # Compute grid size: use sqrt(n_cells) target bins per dimension

        n_total = len(all_placed_cells)

        target_bins = max(4, int(math.sqrt(n_total)))

        grid_size = max(die_w / target_bins, die_h / target_bins, 1.0)



        grid_w = max(1, int(math.ceil(die_w / grid_size)))

        grid_h = max(1, int(math.ceil(die_h / grid_size)))



        # Build spatial hash: grid cell -> list of cell names

        spatial_hash = {}

        for c in all_placed_cells:

            if c not in cells:

                continue

            px, py = placement[c]

            cw = cells[c]['width']

            ch = cells[c]['height']

            gx1 = max(0, int(px // grid_size))

            gy1 = max(0, int(py // grid_size))

            gx2 = min(grid_w - 1, int((px + cw) // grid_size))

            gy2 = min(grid_h - 1, int((py + ch) // grid_size))

            for gx in range(gx1, gx2 + 1):

                for gy in range(gy1, gy2 + 1):

                    spatial_hash.setdefault((gx, gy), []).append(c)



        # Check each grid cell for overlaps

        # Use local sets per grid cell to avoid global MemoryError

        MAX_OVERLAP_PAIRS = 1000

        max_cells_per_cell = 0

        for cell_list in spatial_hash.values():

            max_cells_per_cell = max(max_cells_per_cell, len(cell_list))



        # If any grid cell has >2000 cells, the placement is degenerate

        # (e.g. all cells stacked at the same position). Mark as invalid

        # without checking all O(N^2) pairs.

        if max_cells_per_cell > 2000:

            result.valid = False

            result.errors.append(

                'Degenerate placement: %d cells in one grid cell. '

                'Likely all cells stacked at same position.' % max_cells_per_cell

            )

            result.overlapping_pairs.append(

                ('__degenerate__', '__all_cells__', float(len(all_placed_cells)))

            )

        else:

            # Global dedup set to prevent same pair counted across multiple grid cells

            global_checked = set()

            for cell_list in spatial_hash.values():

                if len(cell_list) < 2:

                    continue

                for i in range(len(cell_list)):

                    for j in range(i + 1, len(cell_list)):

                        c1 = cell_list[i]

                        c2 = cell_list[j]

                        pair = (c1, c2) if c1 < c2 else (c2, c1)

                        if pair in global_checked:

                            continue

                        global_checked.add(pair)

                        if c1 not in cells or c2 not in cells:

                            continue

                        px1, py1 = placement[c1]

                        pw1 = cells[c1]['width']

                        ph1 = cells[c1]['height']

                        px2, py2 = placement[c2]

                        pw2 = cells[c2]['width']

                        ph2 = cells[c2]['height']

                        # AABB overlap test

                        if (px1 < px2 + pw2 and px1 + pw1 > px2 and

                                py1 < py2 + ph2 and py1 + ph1 > py2):

                            overlap_area = (

                                min(px1 + pw1, px2 + pw2) - max(px1, px2)

                            ) * (

                                min(py1 + ph1, py2 + ph2) - max(py1, py2)

                            )

                            result.overlapping_pairs.append((c1, c2, overlap_area))

                            result.valid = False

                            if len(result.overlapping_pairs) >= MAX_OVERLAP_PAIRS:

                                break

                    if len(result.overlapping_pairs) >= MAX_OVERLAP_PAIRS:

                        break

                    if len(global_checked) > 100000:

                        break

                if len(result.overlapping_pairs) >= MAX_OVERLAP_PAIRS:

                    break



    return result



# ============================================================================

# Main evaluation function

# ============================================================================



def evaluate(

    program_path: str,

    *,

    repo_root: Path | None = None,

    benchmark_name: str | None = None,

) -> Any:

    """

    Full evaluation pipeline:

    1. Run candidate program to produce temp/submission.json

    2. Parse and validate submission

    3. Run independent HPWL + legality checks

    4. Return metrics



    Parameters

    ----------

    program_path : str

        Path to the candidate Python program.

    repo_root : Path, optional

        Repository root. Auto-detected if not given.

    benchmark_name : str, optional

        Benchmark to use (e.g., "adaptec1", "adaptec3").

        Defaults to "adaptec1".

    """

    start = time.time()

    repo_root = (

        _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()

    )

    program_path_resolved = str(Path(program_path).expanduser().resolve())



    # Determine benchmark

    if benchmark_name is None:

        benchmark_name = os.environ.get("BENCHMARK_NAME", "adaptec1")



    work_dir = Path(tempfile.mkdtemp(prefix="fe_vlsigp_")).resolve()

    artifacts: dict[str, str] = {}



    metrics: dict[str, float] = {

        "combined_score": INVALID_COMBINED_SCORE,

        "hpwl": 0.0,

        "valid": 0.0,



        "timeout": 0.0,

        "runtime_s": 0.0,

        "n_cells_placed": 0.0,

        "n_fixed_moved": 0.0,

        "n_out_of_bounds": 0.0,

        "n_overlaps": 0.0,

    }



    try:

        # 1. Copy benchmark reference data to work dir

        ref_path = _get_reference_path(repo_root, benchmark_name)

        if not ref_path.is_file():

            available = _list_available_benchmarks(repo_root)

            avail_str = ", ".join(f"{b['name']} ({b['difficulty']})" for b in available)

            artifacts["error_message"] = (

                f"Benchmark '{benchmark_name}' not found. "

                f"Available: {avail_str}"

            )

            metrics["runtime_s"] = float(time.time() - start)

            return _wrap(metrics, artifacts)



        refs_dir = work_dir / "references"

        refs_dir.mkdir(parents=True, exist_ok=True)

        # Copy the benchmark JSON

        shutil.copy2(ref_path, refs_dir / f"{benchmark_name}.json")



        # Also copy difficulty metadata

        diff_path = _get_difficulty_path(repo_root, benchmark_name)

        if diff_path.is_file():

            shutil.copy2(diff_path, refs_dir / f"{benchmark_name}_difficulty.json")



        # 2. Run candidate program

        env = os.environ.copy()

        env["BENCHMARK_NAME"] = benchmark_name



        try:

            proc = subprocess.run(

                [sys.executable, program_path_resolved],

                cwd=str(work_dir),

                env=env,

                capture_output=True,

                text=True,

                timeout=600,

            )

        except subprocess.TimeoutExpired as e:

            metrics["timeout"] = 1.0

            metrics["runtime_s"] = float(time.time() - start)

            artifacts["error_message"] = f"program timeout: {e}"

            return _wrap(metrics, artifacts)



        artifacts["program_stdout"] = _tail(proc.stdout)

        artifacts["program_stderr"] = _tail(proc.stderr)

        artifacts["program_stdout_full"] = _truncate_middle(proc.stdout)

        artifacts["program_stderr_full"] = _truncate_middle(proc.stderr)

        metrics["program_returncode"] = float(proc.returncode)



        # 3. Read submission

        submission_path = work_dir / "temp" / "submission.json"

        if not submission_path.exists():

            submission_path = work_dir / "submission.json"

        if not submission_path.exists():

            artifacts["error_message"] = (

                "submission.json not generated "

                "(checked temp/submission.json and submission.json)"

            )

            metrics["runtime_s"] = float(time.time() - start)

            return _wrap(metrics, artifacts)



        try:

            with open(submission_path, "r", encoding="utf-8") as f:

                submission = json.load(f)

            # Truncate large submissions for artifacts

            sub_str = json.dumps(submission, indent=2)

            if len(sub_str) > 10000:

                artifacts["submission.json"] = sub_str[:5000] + "\n... [truncated] ...\n" + sub_str[-5000:]

            else:

                artifacts["submission.json"] = sub_str

        except Exception as exc:

            artifacts["error_message"] = f"Failed to parse submission.json: {exc}"

            metrics["runtime_s"] = float(time.time() - start)

            return _wrap(metrics, artifacts)



        if "placement" not in submission:

            artifacts["error_message"] = "submission.json missing 'placement'"

            metrics["runtime_s"] = float(time.time() - start)

            return _wrap(metrics, artifacts)



        placement = submission["placement"]



        # 4. Load benchmark data for evaluation

        with open(ref_path, "r", encoding="utf-8") as f:

            benchmark_data = _decompress_netlist(json.load(f))



        metrics["n_cells_placed"] = float(len(placement))



        # 5. Compute HPWL

        hpwl = compute_hpwl(

            placement,

            benchmark_data["netlist"],

            benchmark_data["cells"],

        )

        metrics["hpwl"] = hpwl



        # 6. Legality checks

        legality = check_legality(

            placement,

            benchmark_data["cells"],

            benchmark_data["die"],

            benchmark_data["fixed_cells"],

            benchmark_data["movable_cells"],

            benchmark_data["initial_placement"],

        )



        metrics["n_fixed_moved"] = float(len(legality.moved_fixed))

        metrics["n_out_of_bounds"] = float(len(legality.out_of_bounds))

        metrics["n_overlaps"] = float(len(legality.overlapping_pairs))



        if not legality.valid:

            artifacts["legality_errors"] = json.dumps({

                "moved_fixed": legality.moved_fixed[:100],

                "out_of_bounds": legality.out_of_bounds[:100],

                "overlaps": [

                    {"cell1": p[0], "cell2": p[1], "overlap_area": p[2]}

                    for p in legality.overlapping_pairs[:100]

                ],

                "total_moved_fixed": len(legality.moved_fixed),

                "total_out_of_bounds": len(legality.out_of_bounds),

                "total_overlaps": len(legality.overlapping_pairs),

                "other_errors": legality.errors,

            }, indent=2)



        runtime_s = time.time() - start

        metrics["runtime_s"] = float(runtime_s)





        if legality.valid:

            # Minimization: negate HPWL so higher combined_score = better

            metrics["combined_score"] = -hpwl

            metrics["valid"] = 1.0

        else:

            metrics["combined_score"] = INVALID_COMBINED_SCORE

            metrics["valid"] = 0.0



        return _wrap(metrics, artifacts)

    finally:

        shutil.rmtree(work_dir, ignore_errors=True)





def _wrap(metrics: dict[str, float], artifacts: dict[str, str]) -> Any:

    try:

        from openevolve.evaluation_result import EvaluationResult



        return EvaluationResult(metrics=metrics, artifacts=artifacts)

    except Exception:

        return metrics





if __name__ == "__main__":

    import argparse



    parser = argparse.ArgumentParser(description="VLSI Global Placement Evaluator")

    parser.add_argument("program_path", help="Path to the candidate Python program")

    parser.add_argument("--benchmark", default="adaptec1",

                        help="Benchmark name (adaptec1, adaptec3)")

    args = parser.parse_args()



    result = evaluate(args.program_path, benchmark_name=args.benchmark)

    if hasattr(result, "metrics"):

        output = {"metrics": result.metrics, "artifacts": result.artifacts}

    else:

        output = result

    print(json.dumps(output, indent=2))

