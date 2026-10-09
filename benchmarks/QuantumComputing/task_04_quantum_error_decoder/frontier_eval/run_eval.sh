#!/usr/bin/env bash
# Unified evaluation wrapper for QuantumComputing/task_04_quantum_error_decoder.
#
# This script is intentionally thin: verification/evaluate.py owns the scoring and
# writes metrics.json itself. The wrapper exists to guarantee that a crashed or
# timed-out evaluation still leaves a well-formed, explicitly-invalid metrics.json
# behind, and to keep exit status 0 so the harness reports the candidate-level
# verdict instead of an opaque infrastructure failure.
set -euo pipefail

PYTHON_CMD="${1:?missing python command}"
BENCHMARK_DIR="${2:?missing benchmark dir}"
CANDIDATE_PATH="${3:-}"

if [[ "${BENCHMARK_DIR}" != /* ]]; then
  BENCHMARK_DIR="$(cd "${BENCHMARK_DIR}" && pwd -P)"
fi

if [[ -n "${CANDIDATE_PATH}" && "${CANDIDATE_PATH}" != /* ]]; then
  if [[ -f "${CANDIDATE_PATH}" ]]; then
    CANDIDATE_PATH="$(cd "$(dirname "${CANDIDATE_PATH}")" && pwd -P)/$(basename "${CANDIDATE_PATH}")"
  else
    CANDIDATE_PATH="${BENCHMARK_DIR}/${CANDIDATE_PATH}"
  fi
fi

METRICS_JSON="${BENCHMARK_DIR}/metrics.json"
ARTIFACTS_JSON="${BENCHMARK_DIR}/artifacts.json"
REPORT_JSON="${BENCHMARK_DIR}/eval_report.json"
EVAL_STDOUT="${BENCHMARK_DIR}/eval.stdout.txt"
EVAL_STDERR="${BENCHMARK_DIR}/eval.stderr.txt"
RUN_META="${BENCHMARK_DIR}/run_meta.txt"

rm -f "${METRICS_JSON}" "${ARTIFACTS_JSON}" "${REPORT_JSON}" "${EVAL_STDOUT}" "${EVAL_STDERR}"

START_TS="$(date +%s)"

set +e
"${PYTHON_CMD}" "${BENCHMARK_DIR}/verification/evaluate.py" \
  --candidate "${CANDIDATE_PATH}" \
  --metrics-out "${METRICS_JSON}" \
  --artifacts-out "${ARTIFACTS_JSON}" \
  --report-out "${REPORT_JSON}" \
  >"${EVAL_STDOUT}" 2>"${EVAL_STDERR}"
EVAL_RC=$?
set -e

END_TS="$(date +%s)"
ELAPSED_S=$((END_TS - START_TS))

if [[ ${EVAL_RC} -ne 0 || ! -f "${METRICS_JSON}" ]]; then
  "${PYTHON_CMD}" - "${METRICS_JSON}" "${ARTIFACTS_JSON}" "${EVAL_RC}" "${ELAPSED_S}" "${EVAL_STDERR}" <<'PY'
import json
import sys
from pathlib import Path

metrics_path = Path(sys.argv[1])
artifacts_path = Path(sys.argv[2])
eval_rc = int(sys.argv[3])
elapsed_s = float(sys.argv[4])
stderr_path = Path(sys.argv[5])

metrics = {
    "combined_score": -1e18,
    "valid": 0.0,
    "feasibility_rate": 0.0,
    "eval_returncode": float(eval_rc),
    "runtime_s": elapsed_s,
}
artifacts = {
    "task_name": "QuantumComputing/task_04_quantum_error_decoder",
    "eval_returncode": eval_rc,
    "error_message": "verification/evaluate.py failed before reporting a score",
}
if stderr_path.is_file():
    tail = stderr_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    if tail:
        artifacts["evaluate_stderr_tail"] = "\n".join(tail[-20:])

metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
artifacts_path.write_text(json.dumps(artifacts, indent=2, ensure_ascii=False), encoding="utf-8")
PY
fi

{
  echo "candidate_path=${CANDIDATE_PATH}"
  echo "eval_returncode=${EVAL_RC}"
  echo "runtime_s=${ELAPSED_S}"
  echo "metrics_json=${METRICS_JSON}"
  echo "artifacts_json=${ARTIFACTS_JSON}"
} > "${RUN_META}"

# Report success: the candidate-level verdict lives in metrics.json (valid=0 with
# combined_score=-1e18 on failure), and the harness discards the report on a
# non-zero exit.
exit 0