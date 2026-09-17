"""Python compatibility entry point for task-local evaluation."""

import subprocess
import sys
from pathlib import Path


def main():
    task_root = Path(__file__).parents[1]
    candidate = sys.argv[1] if len(sys.argv) > 1 else "scripts/init.py"
    command = [
        sys.executable,
        "verification/evaluator.py",
        candidate,
        "--json-out",
        "metrics.json",
        "--artifacts-out",
        "artifacts.json",
    ]
    return subprocess.call(command, cwd=task_root)


if __name__ == "__main__":
    raise SystemExit(main())
