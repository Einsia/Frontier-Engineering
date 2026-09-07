#!/usr/bin/env bash
set -euo pipefail

PYTHON_CMD="${1:?missing python command}"
BENCHMARK_DIR="${2:?missing benchmark dir}"
CANDIDATE_PATH="${3:-}"

HANDOUT_DIR="${BENCHMARK_DIR}/malloclab-handout"
MAKE_CLEAN_LOG="${BENCHMARK_DIR}/make_clean.log"
MAKE_LOG="${BENCHMARK_DIR}/make.log"
MDRIVER_STDOUT="${BENCHMARK_DIR}/mdriver.stdout.txt"
MDRIVER_STDERR="${BENCHMARK_DIR}/mdriver.stderr.txt"
MDRIVER_RESULT="${BENCHMARK_DIR}/mdriver_result.json"
METRICS_JSON="${BENCHMARK_DIR}/metrics.json"

# Per-run token for the authenticated result channel.
#
# The candidate's mm.c is compiled into mdriver, so it can write anything it
# likes to mdriver's stdout -- and the score used to be parsed from there. It
# now travels in ${MDRIVER_RESULT}, which only counts if it carries this token.
#
# The token is a shell variable, never exported and never written to disk while
# mdriver runs, so it is not in mdriver's environ and not readable from the
# filesystem. It reaches mdriver on stdin, which mdriver consumes and closes
# before it calls into the allocator, and it reaches the parser on a command
# line that is only built after mdriver has already exited.
RUN_TOKEN="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
if [[ -z "${RUN_TOKEN}" ]]; then
  echo "ERROR: could not generate a run token" >&2
  exit 1
fi

rm -f "${MDRIVER_RESULT}"

cd "${HANDOUT_DIR}"

make clean >"${MAKE_CLEAN_LOG}" 2>&1
make >"${MAKE_LOG}" 2>&1

set +e
printf '%s\n' "${RUN_TOKEN}" \
  | ./mdriver -V -o "${MDRIVER_RESULT}" >"${MDRIVER_STDOUT}" 2>"${MDRIVER_STDERR}"
MDRIVER_RC=$?
set -e

{
  echo "candidate_path=${CANDIDATE_PATH}"
  echo "mdriver_returncode=${MDRIVER_RC}"
} > "${BENCHMARK_DIR}/run_meta.txt"

"${PYTHON_CMD}" "${BENCHMARK_DIR}/frontier_eval/parse_mdriver_result.py" \
  --result-file "${MDRIVER_RESULT}" \
  --expected-token "${RUN_TOKEN}" \
  --stdout-file "${MDRIVER_STDOUT}" \
  --stderr-file "${MDRIVER_STDERR}" \
  --mdriver-returncode "${MDRIVER_RC}" \
  --metrics-out "${METRICS_JSON}"

# Always return 0 here: parsed `metrics.json` already encodes validity/score.
exit 0
