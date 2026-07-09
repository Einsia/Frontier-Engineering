"""FPGA Placement Optimization ? baseline reference solution.

This is the reference implementation used for comparison.
It implements a simple row-scan placer (identical to scripts/init.py).

The expected output for fpga-example1:
  HPWL = 210721
  All three legality gates pass
  combined_score = -210721
"""

from __future__ import annotations

import sys
from pathlib import Path

_src_dir = Path(__file__).resolve().parent.parent / "scripts"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


def main() -> None:
    # Import and delegate to the same logic as scripts/init.py
    from pathlib import Path as _Path

    # Locate benchmark files
    ref_dir = _Path(__file__).resolve().parent.parent / "references"

    # Run the same logic as the initial solver
    import runpy
    init_path = _src_dir / "init.py"
    sys.argv = [
        str(init_path),
        "--nodes", str(ref_dir / "design.nodes"),
        "--pl", str(ref_dir / "design.pl"),
        "--scl", str(ref_dir / "design.scl"),
        "--output", "temp/baseline_solution.pl",
    ]
    runpy.run_path(str(init_path), run_name="__main__")


if __name__ == "__main__":
    main()
