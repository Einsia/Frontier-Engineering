#!/usr/bin/env bash
set -euo pipefail

python_bin="${1:?usage: run_eval.sh PYTHON CANDIDATE}"
candidate="${2:?usage: run_eval.sh PYTHON CANDIDATE}"

exec "$python_bin" verification/evaluator.py "$candidate" \
  --metrics-out metrics.json \
  --artifacts-out artifacts.json
