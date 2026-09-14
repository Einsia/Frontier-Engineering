# Frontier Eval Framework

Evaluation framework for `Frontier-Engineering`.

## Layout

- `frontier_eval/cli.py`: main entrypoint (`python -m frontier_eval`)
- `frontier_eval/tasks/`: benchmark task implementations
- `frontier_eval/algorithms/`: search algorithms (`openevolve`, `abmcts`, `shinkaevolve`)
- `frontier_eval/conf/`: Hydra configs for tasks, algorithms, and LLM backends

## Setup

The intended setup path is now `uv`-based.

From the repo root:

```bash
bash init.sh
source .venvs/frontier-eval-driver/bin/activate
```

That prepares the driver environment used to run `python -m frontier_eval`.

If you want the v1 task runtime environments used by the released `v1` benchmark set:

```bash
bash scripts/env/setup_v1_task_envs.sh
```

Important: this only prepares the framework and the repo-owned runtime environments. Many benchmarks still require task-local dependencies, external assets, Docker, or third-party repos.

Candidate subprocess isolation requires Linux user namespaces and `bubblewrap` (`bwrap`; on Debian/Ubuntu: `sudo apt-get install bubblewrap`). Restricted candidates receive only their declared inputs and have no network; missing isolation support fails the evaluation instead of running without isolation.

Before running a benchmark, always read:

1. `benchmarks/<Domain>/README*.md`
2. `benchmarks/<Domain>/<Task>/README*.md` when present

Treat those task README files as the source of truth for benchmark-local prerequisites.

## Runtime selection

Unified tasks support two runtime selectors:

- `task.runtime.env_name=<name>`: prepend `.venvs/<name>/bin` to `PATH`
- `task.runtime.python_path=uv-env:<name>`: resolve directly to `.venvs/<name>/bin/python`

You can also pass an absolute interpreter path with:

```bash
task.runtime.python_path=/abs/path/to/python
```

The default fallback runtime is `frontier-eval-driver`, but many tasks should use a task-specific runtime instead.

## Quick smoke

These commands are fast and do not require extra benchmark assets:

```bash
python -m frontier_eval task=smoke algorithm=openevolve algorithm.iterations=0
python -m frontier_eval task=smoke algorithm=shinkaevolve algorithm.max_generations=0
python -m frontier_eval task=smoke algorithm=abmcts algorithm.iterations=0
```

## Running a unified benchmark

Example:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/MallocLab \
  algorithm=openevolve \
  algorithm.iterations=10
```

Baseline-only evaluation without any LLM calls:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/MallocLab \
  algorithm=openevolve \
  algorithm.iterations=0
```

If a task needs a dedicated runtime:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ReactionOptimisation/snar_multiobjective \
  task.runtime.python_path=uv-env:frontier-v1-summit \
  algorithm=openevolve \
  algorithm.iterations=0
```

EngDesign still runs through the unified pathway, but its benchmark wrapper decides whether to use Docker or local execution.

## Unified benchmark metadata

Under `benchmarks/<Domain>/<Task>/frontier_eval/`:

```text
initial_program.txt       # required
candidate_destination.txt # optional
eval_command.txt          # required
eval_cwd.txt              # optional
agent_files.txt           # optional
copy_files.txt            # optional
readonly_files.txt        # optional
artifact_files.txt        # optional
constraints.txt           # optional
```

Useful placeholders in `eval_command.txt`:

- `{python}`
- `{candidate}`
- `{benchmark}`
- `{sandbox}`
- `{repo_root}`
- `{benchmark_source}`
- `{benchmark_id}`

The evaluator expects:

- `metrics.json`
- optionally `artifacts.json`

If `valid` or `combined_score` are missing, the unified evaluator applies sane fallbacks.

## Batch runs

General form:

```bash
python -m frontier_eval.batch --matrix frontier_eval/conf/batch/example_matrix.yaml
```

Released `v1` matrix:

```bash
python -m frontier_eval.batch --matrix frontier_eval/conf/batch/v1.yaml
```

Operator workflow and host-side setup are documented in [`run.md`](../run.md) and [`run_zh-CN.md`](../run_zh-CN.md).

Task entries in a batch matrix may carry per-task runtime overrides, for example:

```yaml
tasks:
  - name: unified
    label: ReactionOptimisation/dtlz2_pareto
    overrides:
      - task.benchmark=ReactionOptimisation/dtlz2_pareto
      - task.runtime.python_path=uv-env:frontier-v1-summit
```

## v1 runtime layout

The current v1 task runtimes are:

- `frontier-v1-main`
- `frontier-v1-summit`
- `frontier-v1-sustaindc`
- `frontier-v1-kernel`

`openff-dev` remains a special runtime because the OpenFF toolchain is not fully reproducible with `uv` alone as of 2026.
Bootstrap it separately with:

```bash
bash scripts/bootstrap/install_openff_dev.sh
```

Setup and validation helpers:

- `bash scripts/env/setup_v1_task_envs.sh`
- `bash scripts/batch/validate_v1_task_envs.sh`
- `python scripts/ops/audit_unified_metadata_readonly.py [--strict]`

## Optional third-party repos

Some algorithms and benchmarks still depend on local checkouts under `third_party/`.

Use the bootstrap helper to provision them:

```bash
python scripts/bootstrap/fetch_task_assets.py --target algorithms
python scripts/bootstrap/fetch_task_assets.py --target shinkaevolve
python scripts/bootstrap/fetch_task_assets.py --target abmcts
```

Examples:

```bash
mkdir -p third_party
git clone https://github.com/SakanaAI/treequest.git third_party/treequest
git clone https://github.com/thuml/PhySense.git third_party/PhySense
```

For `shinkaevolve`, use a local checkout if you need to patch provider metadata or debug the adapter.

## Environment variables

Use a local `.env`:

```bash
cp .env.example .env
```

`python -m frontier_eval ...` automatically searches upward and loads the nearest `.env`.

Optimization runs need `OPENAI_API_KEY`; baseline-only runs with `algorithm.iterations=0` do not.
