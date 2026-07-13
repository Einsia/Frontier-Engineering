#!/usr/bin/env bash
set -euo pipefail

PYTHON_CMD="${1:?missing Python interpreter}"
CANDIDATE_PATH="${2:?missing candidate path}"

exec "${PYTHON_CMD}" verification/evaluator.py "${CANDIDATE_PATH}" \
  --json-out metrics.json \
  --artifacts-out artifacts.json
