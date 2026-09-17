# Frontier-Engineering Repo Checklist

Use this file when you need exact repo placement and validation details.

## Prefer Unified When Possible

The repo already supports benchmark-local metadata through `frontier_eval/tasks/unified/`.
Prefer that path for new tasks that can be evaluated by a shell command plus `metrics.json`.

Useful files to inspect:

1. `frontier_eval/README.md`
2. `frontier_eval/README_zh-CN.md`
3. `frontier_eval/tasks/unified/spec.py`
4. `benchmarks/CommunicationEngineering/PMDSimulation/frontier_eval/`

Minimum unified metadata under `benchmarks/<Domain>/<Task>/frontier_eval/`:

1. `initial_program.txt`
2. `eval_command.txt`

Commonly useful optional metadata:

1. `candidate_destination.txt`
2. `eval_cwd.txt`
3. `agent_files.txt`
4. `artifact_files.txt`
5. `readonly_files.txt`
6. `constraints.txt`

Evaluation convention:

1. Make `eval_command.txt` produce `metrics.json`.
2. Include numeric `combined_score`.
3. Include numeric or boolean `valid`.
4. Use nonzero exit codes for fatal evaluation failure.

## Use A Bespoke Wrapper Only When Needed

Create a dedicated `frontier_eval/tasks/<task>/` package only when the benchmark needs Python-driven sandbox logic.

Representative files:

1. `frontier_eval/tasks/quadruped_gait/task.py`
2. `frontier_eval/tasks/mla/task.py`
3. `frontier_eval/tasks/mla/evaluator/python.py`
4. `frontier_eval/conf/task/quadruped_gait.yaml`

Minimum bespoke wrapper additions:

1. `frontier_eval/tasks/<task>/task.py`
2. `frontier_eval/tasks/<task>/__init__.py`
3. `frontier_eval/tasks/<task>/evaluator/python.py`
4. `frontier_eval/tasks/<task>/evaluator/__init__.py`
5. `frontier_eval/conf/task/<task>.yaml`

## Benchmark Folder Shape

Most benchmark folders should include:

1. `Task.md`
2. `Task_zh-CN.md`
3. `README.md`
4. `baseline/`
5. `verification/`
6. `frontier_eval/`

Common optional additions:

1. `README_zh-CN.md`
2. `references/`
3. `runtime/`
4. `data/`
5. `scripts/`

## Data Provenance Checklist

Before committing a benchmark with any nontrivial data payload or instance file, record:

1. The primary source URL, paper, or upstream repository.
2. The exact dataset version, release tag, instance name, or snapshot date.
3. Whether files in this repo are raw, filtered, transformed, or synthetic.
4. The preprocessing script or manual transformation steps.
5. The redistribution or license status.

Recommended placement:

1. Put a short provenance summary in `README.md`.
2. Mention the canonical source in `Task.md` and `Task_zh-CN.md`.
3. Keep preprocessing code in `scripts/` or `references/` when practical.
4. Avoid committing opaque processed files without a reconstruction path.

For classic benchmark instances such as FT10 or LA16, cite the benchmark family and pin the exact instance names instead of relying on informal copies.

Representative examples:

1. `benchmarks/Robotics/QuadrupedGaitOptimization/`
2. `benchmarks/CommunicationEngineering/PMDSimulation/`
3. `benchmarks/KernelEngineering/FlashAttention/`

## Candidate Interface Checklist

Before implementation, pin down:

1. Which file is the editable candidate file.
2. Where that candidate file is copied inside the sandbox.
3. Which function or class entrypoint the evaluator expects.
4. Which files are read-only.
5. Which outputs are used to compute score.

Prefer one editable file and one well-named entrypoint.

## Validation Checklist

Run these checks before considering the task contributed:

1. Run the baseline directly inside the benchmark folder.
2. Confirm the direct evaluator returns a finite score and `valid=1` for the baseline or init candidate.
3. Run the benchmark through `frontier_eval`.
4. Confirm the benchmark is reading the intended source files, instance set, or local snapshot.
5. Confirm the baseline score is reproducible across at least two runs when practical.
6. Confirm metrics degrade or fail when the candidate is intentionally broken.
7. If the task is meant to be optimizable, run a 10-step sanity check with `eval_single.sh` and see whether the best valid score improves over the initial candidate.
8. Confirm logs or artifacts are preserved where the user can inspect them.

Useful smoke command:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=<Domain>/<Task> \
  algorithm.iterations=0
```

If the task does not fit `unified`, run the corresponding dedicated task config instead.

Useful short optimization sanity check:

```bash
./eval_single.sh task=unified task.benchmark=<Domain>/<Task>
```

If the benchmark needs a specific Python executable or runtime overrides, pass them through the same script:

```bash
PYTHON_BIN=/mnt/shared-storage-user/p1-shared/luotianwei/Frontier-Engineering/.venv/bin/python \
./eval_single.sh \
  task=unified \
  task.benchmark=<Domain>/<Task> \
  task.runtime.use_conda_run=false \
  task.runtime.python_path=/mnt/shared-storage-user/p1-shared/luotianwei/Frontier-Engineering/.venv/bin/python
```

Interpretation rule:

1. `valid=1` with a finite score is the minimum bar for “can be scored”.
2. A visible best-score improvement within 10 steps is the preferred bar for “quality-checked and optimization-ready”.
3. If the 10-step run fails to improve, document that explicitly as a remaining risk instead of calling the benchmark fully validated.
