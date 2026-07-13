#!/usr/bin/env bash
set -euo pipefail
candidate="${1:-scripts/init.py}"
"${PYTHON:-python}" verification/evaluator.py "$candidate" --json-out metrics.json --artifacts-out artifacts.json
