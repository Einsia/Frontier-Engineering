#!/usr/bin/env bash
set -euo pipefail

PYTHON_CMD="${1:?missing python command}"
BENCHMARK_DIR="${2:?missing benchmark directory}"
CANDIDATE_PATH="${3:?missing candidate path}"

"${PYTHON_CMD}" "${BENCHMARK_DIR}/verification/evaluator.py" "${CANDIDATE_PATH}" \
  --metrics-out "${BENCHMARK_DIR}/metrics.json" \
  --artifacts-out "${BENCHMARK_DIR}/artifacts.json"
