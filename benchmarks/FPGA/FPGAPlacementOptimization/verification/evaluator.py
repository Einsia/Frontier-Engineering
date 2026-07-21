"""Evaluator for FPGA Placement Optimization.

This evaluator:
1. Runs the candidate program (scripts/init.py) to produce solution.pl
2. Validates EVOLVE-BLOCK boundary integrity
3. Parses the output solution.pl
4. Checks legality gates (G1: site-type, G2: capacity, G3: carry-chain)
5. Computes HPWL
6. Returns metrics dict with combined_score

Benchmark selection:
  Default: references/design.* (fpga-example1, fast smoke test)
  --benchmark FPGA01: references/ispd2016/FPGA01/ (ISPD 2016 design)
  --benchmark FPGA02..FPGA12: corresponding ISPD 2016 design
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

# Ensure canonical.py is importable when running from any working directory
_evaluator_dir = Path(__file__).resolve().parent
if str(_evaluator_dir) not in sys.path:
    sys.path.insert(0, str(_evaluator_dir))

from canonical import (
    parse_nodes,
    parse_nets,
    parse_pl,
    parse_scl,
    compute_hpwl_canonical,
    check_site_type_compatibility,
    check_site_capacity,
    check_carry_chain_integrity,
)

INVALID_COMBINED_SCORE = -1e18

# Known ISPD 2016 benchmark designs
ISPD2016_DESIGNS = {f"FPGA{i:02d}" for i in range(1, 13)}

# Protected function names that must remain OUTSIDE the EVOLVE-BLOCK
_PROTECTED_FUNCTIONS = [
    "def parse_nodes",
    "def parse_pl",
    "def parse_scl",
    "def write_pl",
    "def main()",
]


def validate_evolve_boundary(program_path: str) -> tuple[bool, str]:
    """Verify that critical read-only code is OUTSIDE the EVOLVE-BLOCK.

    The EVOLVE-BLOCK should only wrap the placement algorithm functions.
    Parser functions, output writer, and CLI entry point must remain
    outside the block to preserve the benchmark contract.

    Returns (passes, error_message).
    """
    try:
        with open(program_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return False, f"cannot read candidate program: {e}"

    # Locate EVOLVE-BLOCK boundaries
    start_line = None
    end_line = None
    for i, line in enumerate(lines):
        if "# EVOLVE-BLOCK-START" in line:
            start_line = i  # 0-indexed
        if "# EVOLVE-BLOCK-END" in line:
            end_line = i

    if start_line is None:
        return False, "EVOLVE-BLOCK-START marker not found in candidate program"
    if end_line is None:
        return False, "EVOLVE-BLOCK-END marker not found in candidate program"
    if end_line <= start_line:
        return False, "EVOLVE-BLOCK-END appears before EVOLVE-BLOCK-START"

    # Check that each protected function is OUTSIDE the block
    for line_num, line_text in enumerate(lines):
        stripped = line_text.strip()
        for pattern in _PROTECTED_FUNCTIONS:
            if stripped.startswith(pattern):
                if start_line <= line_num <= end_line:
                    return False, (
                        f"protected function '{pattern}' found inside EVOLVE-BLOCK "
                        f"(line {line_num + 1}). This function is part of the frozen "
                        f"benchmark contract and must remain outside the EVOLVE-BLOCK."
                    )
                break  # matched one pattern, move to next line

    return True, ""


def _find_repo_root(start: Path | None = None) -> Path:
    if "FRONTIER_ENGINEERING_ROOT" in os.environ:
        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "frontier_eval").is_dir() and (parent / "benchmarks").is_dir():
            return parent
    return Path.cwd().resolve()


def _resolve_benchmark_dir(repo_root: Path, benchmark: str | None) -> Path:
    benchmark_rel = Path("benchmarks") / "FPGA" / "FPGAPlacementOptimization"
    base_dir = repo_root / benchmark_rel / "references"
    if not base_dir.is_dir():
        for prefix in [Path.cwd().resolve(), repo_root]:
            candidate = prefix / benchmark_rel / "references"
            if candidate.is_dir():
                base_dir = candidate
                break
    if benchmark is None:
        return base_dir
    design_upper = benchmark.upper()
    if design_upper not in ISPD2016_DESIGNS:
        valid = sorted(ISPD2016_DESIGNS)
        raise ValueError(f"Unknown ISPD 2016 design: '{benchmark}'. Valid options: {', '.join(valid)}")
    design_dir = base_dir / "ispd2016" / design_upper
    if not design_dir.is_dir():
        nl = chr(10)
        msg = (
            "ISPD 2016 benchmark dataset not found for '" + design_upper + "'."
            + nl + nl
            + "  Expected location: " + str(design_dir)
            + nl + nl
            + "  The ISPD 2016 benchmark suite is NOT bundled with this repository"
            + nl + "  due to its size (~1 GB). To use --benchmark, download and set up"
            + nl + "  the dataset manually:"
            + nl + nl
            + "    1. Download the official ISPD 2016 FPGA Placement Contest benchmarks from:"
            + nl + "       http://www.ispd.cc/contests/16/benchmarks.html"
            + nl + nl
            + "    2. Extract each design into:"
            + nl + "       " + str(base_dir / "ispd2016")
            + nl + nl
            + "    3. The directory structure should be:"
            + nl + "       references/ispd2016/FPGA01/design.nodes  (and .nets, .pl, .scl, ...)"
            + nl + "       references/ispd2016/FPGA02/design.nodes"
            + nl + "       ..."
            + nl + nl
            + "  See the Dataset Setup section in README.md for detailed instructions."
            + nl + "  To run without downloading, omit --benchmark to use the bundled"
            + nl + "  fpga-example1 design instead."
        )
        raise FileNotFoundError(msg)
    return design_dir


def _tail(text: str, limit: int = 8000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _truncate_middle(text: str, limit: int = 200_000) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, (limit - 128) // 2)
    omitted = len(text) - 2 * keep
    return text[:keep] + f"\n\n[... truncated {omitted} chars ...]\n\n" + text[-keep:]


def evaluate(program_path: str, *, benchmark: str | None = None, repo_root: Path | None = None) -> Any:
    """Full evaluation pipeline.

    1. Validate EVOLVE-BLOCK boundary integrity
    2. Run candidate program to produce solution.pl
    3. Parse benchmark files and candidate placement
    4. Check legality gates (G1, G2, G3)
    5. Compute HPWL
    6. Return metrics dict

    Args:
        program_path: Path to the candidate program (scripts/init.py).
        benchmark: Optional ISPD 2016 design name (e.g. 'FPGA01').
                   Defaults to fpga-example1 (references/).
        repo_root: Repository root. Auto-detected if not provided.
    """
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root
    benchmark_dir = _resolve_benchmark_dir(repo_root, benchmark)

    # Benchmark input files
    nodes_path = benchmark_dir / "design.nodes"
    nets_path = benchmark_dir / "design.nets"
    pl_path = benchmark_dir / "design.pl"
    scl_path = benchmark_dir / "design.scl"

    artifacts: dict[str, str] = {}
    metrics: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Step 0: Validate EVOLVE-BLOCK boundary
    # ------------------------------------------------------------------
    boundary_ok, boundary_msg = validate_evolve_boundary(program_path)
    if not boundary_ok:
        artifacts["evolve_boundary_error"] = boundary_msg
        metrics["gate_site_type"] = 0.0
        metrics["gate_capacity"] = 0.0
        metrics["gate_carry_chain"] = 0.0
        metrics["hpwl"] = 0.0
        metrics["valid"] = 0.0
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    # ------------------------------------------------------------------
    # Step 1: Run candidate program in a temporary directory
    # ------------------------------------------------------------------
    work_dir = Path(tempfile.mkdtemp(prefix="fpga_eval_"))

    try:
        # Copy benchmark files to work dir so candidate can resolve them
        # (candidate falls back to references/ automatically)
        pass

        # Run the candidate program
        cmd = [
            sys.executable,
            os.path.abspath(program_path),
            "--output", str(work_dir / "solution.pl"),
        ]

        # Pass benchmark paths explicitly if they differ from references/
        if benchmark is not None:
            cmd.extend(["--nodes", str(nodes_path)])
            cmd.extend(["--pl", str(pl_path)])
            cmd.extend(["--scl", str(scl_path)])

        env = os.environ.copy()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,
                env=env,
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

        if proc.returncode != 0:
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"crashed with return code {proc.returncode}"
            return _wrap(metrics, artifacts)

        # ------------------------------------------------------------------
        # Step 2: Read benchmark data
        # ------------------------------------------------------------------
        instances = parse_nodes(str(nodes_path))
        netlist = parse_nets(str(nets_path))
        scl_data = parse_scl(str(scl_path))
        ref_pl = parse_pl(str(pl_path))

        # ------------------------------------------------------------------
        # Step 3: Read candidate solution
        # ------------------------------------------------------------------
        solution_path = work_dir / "solution.pl"
        if not solution_path.is_file():
            artifacts["error_message"] = "solution.pl not generated by candidate"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        candidate_pl = parse_pl(str(solution_path))
        artifacts["num_placed"] = str(len(candidate_pl))

        # ------------------------------------------------------------------
        # Step 4: Validate completeness
        # ------------------------------------------------------------------
        missing_movable: list[str] = []
        for name, ctype in instances:
            if name not in ref_pl and name not in candidate_pl:
                missing_movable.append(name)

        moved_fixed: list[str] = []
        for name, (rx, ry, rz) in ref_pl.items():
            if name in candidate_pl:
                cx, cy, cz = candidate_pl[name]
                if (cx, cy, cz) != (rx, ry, rz):
                    moved_fixed.append(name)

        errors: list[str] = []
        if missing_movable:
            errors.append(f"{len(missing_movable)} movable instances missing from solution")
        if moved_fixed:
            errors.append(f"{len(moved_fixed)} fixed instances were moved")

        if errors:
            artifacts["validation_errors"] = ", ".join(errors)
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        # ------------------------------------------------------------------
        # Step 5: Check legality gates
        # ------------------------------------------------------------------
        g1_ok, g1_violations = check_site_type_compatibility(candidate_pl, instances, scl_data)
        g2_ok, g2_violations = check_site_capacity(candidate_pl, instances, scl_data)
        g3_ok, g3_violations = check_carry_chain_integrity(candidate_pl, instances)

        metrics["gate_site_type"] = 1.0 if g1_ok else 0.0
        metrics["gate_capacity"] = 1.0 if g2_ok else 0.0
        metrics["gate_carry_chain"] = 1.0 if g3_ok else 0.0

        if not g1_ok:
            artifacts["gate_site_type_violations"] = "\n".join(g1_violations[:20])
        if not g2_ok:
            artifacts["gate_capacity_violations"] = "\n".join(g2_violations[:20])
        if not g3_ok:
            artifacts["gate_carry_chain_violations"] = "\n".join(g3_violations[:20])

        all_gates_pass = g1_ok and g2_ok and g3_ok

        # ------------------------------------------------------------------
        # Step 6: Compute HPWL
        # ------------------------------------------------------------------
        hpwl = compute_hpwl_canonical(candidate_pl, netlist)
        metrics["hpwl"] = float(hpwl)

        runtime_s = time.time() - start
        metrics["runtime_s"] = float(runtime_s)

        if all_gates_pass:
            metrics["combined_score"] = -float(hpwl)
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
    parser = argparse.ArgumentParser(description="FPGA Placement Optimization Evaluator")
    parser.add_argument("program_path", help="Path to the candidate program (scripts/init.py)")
    parser.add_argument(
        "--benchmark", "-b", default=None,
        help="ISPD 2016 design name (e.g. FPGA01..FPGA12). Default: fpga-example1 (references/)."
    )
    args = parser.parse_args()

    try:
        result = evaluate(args.program_path, benchmark=args.benchmark)
    except (ValueError, FileNotFoundError) as e:
        print(json.dumps({"error": str(e)}, indent=2))
        sys.exit(1)

    if hasattr(result, "metrics"):
        output = {"metrics": result.metrics, "artifacts": result.artifacts}
    else:
        output = result
    print(json.dumps(output, indent=2))
