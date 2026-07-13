#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: run_eval.sh PYTHON CANDIDATE METRICS_JSON ARTIFACTS_JSON" >&2
  exit 2
fi

python_path=$1
candidate_path=$2
metrics_path=$3
artifacts_path=$4

exec "$python_path" verification/evaluator.py "$candidate_path" \
  --metrics-out "$metrics_path" \
  --artifacts-out "$artifacts_path"
