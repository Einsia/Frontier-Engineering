#!/usr/bin/env bash
# Regenerates /app/results/output_{items,stacks,trucks}.csv from /app/data alone.
# Deterministic: fixed ordering, no randomness, no wall-clock dependent decisions, single thread.
set -euo pipefail
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${1:-}" ]; then
  DATA_DIR="$1"
elif [ -f /app/data/campaign/input_items.csv ]; then
  DATA_DIR=/app/data/campaign
else
  DATA_DIR=/app/data
fi
OUT_DIR="${2:-/app/results}"
BUILD_DIR="$(mktemp -d /tmp/roadef_build.XXXXXX)"
trap 'rm -rf "$BUILD_DIR"' EXIT
g++ -O2 -std=c++17 -ffp-contract=off -o "$BUILD_DIR/solver" "$SRC_DIR/solver.cpp"
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/output_items.csv" "$OUT_DIR/output_stacks.csv" "$OUT_DIR/output_trucks.csv"
"$BUILD_DIR/solver" "$DATA_DIR" "$OUT_DIR"
echo "Outputs written to $OUT_DIR"
