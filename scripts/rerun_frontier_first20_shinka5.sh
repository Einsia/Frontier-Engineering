#!/usr/bin/env bash
set -euo pipefail

ROOT="/mnt/shared-storage-user/p1-shared/luotianwei/Frontier-Engineering"
cd "$ROOT"

PY="${PYTHON_BIN:-./.venv/bin/python}"
MATRIX="${MATRIX_PATH:-frontier_eval/conf/batch/frontier_first20_shinkaevolve5.yaml}"
BATCH_ROOT="${1:-runs/batch/frontier_first20_shinkaevolve5__20260313_162247__46e57490}"

mapfile -t TASKS < <(
  "$PY" - <<'PY'
from omegaconf import OmegaConf

cfg = OmegaConf.load("frontier_eval/conf/batch/frontier_first20_shinkaevolve5.yaml")
for task in cfg["tasks"]:
    print(task)
PY
)

cmd=("$PY" -m frontier_eval.batch --matrix "$MATRIX" --in-place --batch-root "$BATCH_ROOT")
for task in "${TASKS[@]}"; do
  cmd+=(--tasks "$task")
done

printf 'Running:'
for arg in "${cmd[@]}"; do
  printf ' %q' "$arg"
done
printf '\n'

"${cmd[@]}"
"$PY" scripts/summarize_batch_run.py "$BATCH_ROOT"

echo "BATCH_ROOT=$BATCH_ROOT"
