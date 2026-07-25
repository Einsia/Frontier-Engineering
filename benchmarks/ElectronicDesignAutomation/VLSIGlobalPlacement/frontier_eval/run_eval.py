#!/usr/bin/env python3
"""Unified-task evaluation wrapper for VLSI Global Placement.

This script is invoked by the Frontier Eval unified task framework.
It runs the evaluator and writes metrics.json and artifacts.json.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="VLSI Global Placement Eval Wrapper")
    parser.add_argument("--candidate", required=True, help="Path to candidate program")
    parser.add_argument("--metrics-out", default="metrics.json", help="Path to write metrics JSON")
    parser.add_argument("--artifacts-out", default="artifacts.json", help="Path to write artifacts JSON")
    args = parser.parse_args()

    # Ensure we can import the evaluator
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "verification"))

    from evaluator import evaluate

    # Determine benchmark name from environment or default
    benchmark_name = os.environ.get("BENCHMARK_NAME", "adaptec1")

    # Run evaluation
    result = evaluate(args.candidate, benchmark_name=benchmark_name)

    if hasattr(result, "metrics"):
        metrics = result.metrics
        artifacts = result.artifacts
    elif isinstance(result, dict):
        metrics = result.get("metrics", {})
        artifacts = result.get("artifacts", {})
    else:
        metrics = {"error": 1.0, "combined_score": -1e18}
        artifacts = {"error_message": f"Unexpected result type: {type(result)}"}

    # Write metrics.json
    with open(args.metrics_out, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # Write artifacts.json
    with open(args.artifacts_out, "w", encoding="utf-8") as f:
        json.dump(artifacts, f, indent=2)

    print(f"Metrics written to {args.metrics_out}")
    print(f"Artifacts written to {args.artifacts_out}")
    print(f"combined_score: {metrics.get('combined_score', 'N/A')}")
    print(f"valid: {metrics.get('valid', 'N/A')}")


if __name__ == "__main__":
    main()
