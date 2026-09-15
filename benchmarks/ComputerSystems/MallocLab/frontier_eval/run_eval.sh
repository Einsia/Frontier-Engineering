#!/usr/bin/env bash
set -euo pipefail

PYTHON_CMD="${1:-python3}"
BENCHMARK_DIR="${2:?benchmark directory is required}"
CANDIDATE="${3:-${BENCHMARK_DIR}/malloclab-handout/mm.c}"
REPO_ROOT="${FRONTIER_ENGINEERING_ROOT:-}"
if [[ -z "${REPO_ROOT}" ]]; then
  REPO_ROOT="$(cd "${BENCHMARK_DIR}/../../.." && pwd)"
fi

exec "${PYTHON_CMD}" "${REPO_ROOT}/benchmarks/_shared/malloc_isolation.py" \
  "${CANDIDATE}" --benchmark "${BENCHMARK_DIR}" \
  --metrics-out "${BENCHMARK_DIR}/metrics.json" \
  --details-out "${BENCHMARK_DIR}/malloc_details.json"
