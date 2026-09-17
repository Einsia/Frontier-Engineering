---
name: frontier-benchmark-contributor
description: Create and refine Frontier-Engineering benchmark contributions from research/engineering problem ideas, third-party libraries, or known benchmark instances. Use when Codex needs to choose feasible topics, verify authentic and traceable data sources, turn a candidate task into a reproducible benchmark, design the editable agent interface, add baseline and evaluation files, and integrate the result into `benchmarks/` and `frontier_eval/`. Especially useful for benchmark triage, single-file task wrapping, unified-task metadata setup, and repo-specific benchmark contribution work.
---

# Frontier Benchmark Contributor

## Overview

Turn a loose task idea into a Frontier-Engineering benchmark that is small, reproducible, and evaluable by the existing repo tooling.
Prefer benchmark shapes that expose a narrow candidate interface, have a stable baseline, and run repeatedly without large datasets, GUI dependencies, or long training loops.
Treat data provenance as a hard requirement: every dataset, benchmark instance, parameter table, and historical time series must have a real source, a clear transformation path, and wording that does not over-claim authenticity.
Treat benchmark quality checks as a hard requirement too: a contributed task is not "done" just because the baseline runs once. It should be able to produce a valid numeric score, and when possible it should show a real improvement signal in a short `frontier_eval` run such as a 10-step `eval_single.sh` check.

## Triage The Candidate Pool

Start by shrinking the candidate pool before writing code.
Reject candidates with unclear data provenance before evaluating implementation effort.

Score each candidate against six questions:

1. Can the evaluator run offline with bounded runtime and memory?
2. Can the candidate interface be reduced to one file or one narrow function entrypoint?
3. Does the task rely on authentic, traceable data or benchmark instances from a primary source?
4. Is there a trustworthy baseline from the referenced library, dataset, or benchmark instance?
5. Can validity be checked mechanically with deterministic or low-variance metrics?
6. Can the task be explained clearly in `Task.md` and `Task_zh-CN.md` without external hidden context?

Prefer tasks that answer "yes" to all six.
Reject or heavily simplify tasks that require long RL training, online data fetches, GPU-only pipelines, large opaque datasets, simulator stacks that are hard to pin down, or data copied from secondary blog posts and mirrors without a canonical source.

When the user provides a long list, shortlist at most three candidates before implementation.
Prefer "one excellent benchmark landed end-to-end" over a broad but shallow plan.

For the current candidate family in this repo, load [candidate-triage.md](./references/candidate-triage.md) when you need a practical ranking of likely-easy versus likely-heavy tasks.

## Enforce Data Provenance

Treat source authenticity as part of benchmark validity, not just documentation quality.

For any real dataset, public benchmark instance, or historical series:

1. Cite the primary paper, official repository, or official dataset page.
2. Record the exact instance name, release, version, or snapshot date.
3. State whether the repo contains raw data, a processed derivative, or a synthetic stand-in.
4. Explain every nontrivial transformation from source data to benchmark-ready files.
5. Confirm the license or redistribution status before vendoring files into the repo.

Do not present fabricated, hand-copied, or weakly sourced data as if it were canonical benchmark data.
If you use synthetic data for practicality, label it explicitly as synthetic, fix the random seed or generator procedure, and describe why the synthetic construction is an acceptable proxy.

Prefer:

1. Official benchmark instances such as FT10 and LA16 from recognized benchmark collections.
2. Official library examples or reference datasets bundled with the upstream project.
3. Public market, operations, or engineering datasets with stable identifiers and clear licensing.

Avoid:

1. Blog reposts of benchmark tables.
2. Unverifiable CSV files copied from forums or random GitHub forks.
3. "Historical data" without ticker universe, time range, adjustment rules, and source declaration.
4. Derived benchmark files whose preprocessing steps cannot be reconstructed.

## Choose The Integration Path

Prefer the existing `unified` task path unless there is a concrete reason not to.

Use `task=unified` when the benchmark can be described by benchmark-local metadata and a shell evaluation command:

1. Candidate file lives inside the benchmark folder.
2. Evaluation can be launched from `eval_command.txt`.
3. Metrics can be written to `metrics.json`.
4. Artifact collection can be handled by `artifact_files.txt`.
5. No custom Python-side sandbox orchestration is needed.

Use a bespoke `frontier_eval/tasks/<task>` wrapper only when at least one of these is true:

1. The evaluator must mutate or back up multiple files before running.
2. The benchmark needs nontrivial Python-side setup or teardown.
3. The framework must inspect outputs programmatically beyond normal `metrics.json` parsing.
4. The task needs compatibility logic that does not fit cleanly in benchmark-local scripts.

Inspect `frontier_eval/README.md`, `frontier_eval/README_zh-CN.md`, and [repo-checklist.md](./references/repo-checklist.md) when deciding between the two.

## Design The Benchmark Shape

Lock down the task shape before creating files.

Define all of the following explicitly:

1. Immutable world model: simulator, optimizer, instance data, or reference formulas that the agent must not change.
2. Editable surface: the single file, function, or policy the agent is allowed to modify.
3. Baseline: the reference implementation to compare against.
4. Data provenance: canonical source, version or snapshot date, license status, and preprocessing path.
5. Metrics: `combined_score`, `valid`, and any secondary metrics worth logging.
6. Constraints: runtime limit, memory limit, reproducibility expectations, forbidden side effects.
7. Expected artifacts: logs, schedules, plots, or summary tables worth collecting.

Prefer one of these agent surfaces:

1. `solve(instance) -> solution`
2. `plan_path(map, start, goal) -> path`
3. `schedule_fab(state) -> action`
4. `dispatch_rule(job_state) -> priority`
5. `custom_kernel(data) -> output`

Avoid wide interfaces with many mutable files unless the benchmark genuinely needs them.

## Build The Files

Create the benchmark under `benchmarks/<Domain>/<Task>/`.
Mirror existing repo conventions instead of inventing a new layout.

For most new tasks, include:

1. `Task.md`
2. `Task_zh-CN.md`
3. `README.md`
4. `baseline/`
5. `verification/`
6. `frontier_eval/`

Add `README_zh-CN.md`, `references/`, `runtime/`, or `data/` only when they materially help.
If the task uses external or processed data, add explicit source notes in the README and keep any preprocessing script or provenance note close to the data files.

If using `unified`, create benchmark metadata files under `frontier_eval/` and keep the evaluator benchmark-local.
If using a bespoke wrapper, also add:

1. `frontier_eval/tasks/<task>/task.py`
2. `frontier_eval/tasks/<task>/evaluator/python.py`
3. `frontier_eval/tasks/<task>/__init__.py`
4. `frontier_eval/conf/task/<task>.yaml`

Use [repo-checklist.md](./references/repo-checklist.md) for the concrete file checklist and representative examples already present in this repository.

## Write The Task Prompt

Make the task prompt operational, not promotional.

State:

1. What the agent may edit.
2. What inputs are fixed.
3. Where the fixed data or benchmark instances came from.
4. What outputs are expected.
5. How validity is checked.
6. How score is computed.
7. Which baseline or reference implementation is available.

Use concrete paths and function signatures.
Mention exact filenames the user should inspect or modify.
If the task comes from a classic benchmark instance such as FT10 or LA16, include the instance name and the known optimal or baseline score.
If the task uses market data, experimental data, or processed benchmark files, name the provider, time interval, preprocessing rules, and whether the data is redistributed or regenerated locally.

## Validate Before Calling The Task Done

Run the simplest direct benchmark command first, then the Frontier wrapper.

Check at least:

1. Baseline execution succeeds from a clean state.
2. The direct benchmark command writes a finite numeric score and `valid=1` for the baseline or init candidate.
3. The benchmark writes stable metrics.
4. The benchmark is using the intended data snapshot or instance set, not an accidental local variant.
5. Invalid candidate behavior maps to `valid=0`.
6. The candidate cannot silently modify protected files.
7. The task can run through `frontier_eval` with zero or minimal iterations.
8. When the task is intended for evolutionary optimization, run a short optimization sanity check such as a 10-step `eval_single.sh` run and check whether there is at least some valid improvement signal over the initial candidate.

For `unified`, prefer a smoke command of the form:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=<Domain>/<Task> \
  algorithm.iterations=0
```

If the benchmark needs a specific Python or conda environment, document it in the benchmark README and task metadata.

For short optimization validation in this repository, prefer the repo helper script:

```bash
./eval_single.sh task=unified task.benchmark=<Domain>/<Task>
```

If the benchmark needs `.venv` or non-default runtime overrides, pass them explicitly:

```bash
PYTHON_BIN=/mnt/shared-storage-user/p1-shared/luotianwei/Frontier-Engineering/.venv/bin/python \
./eval_single.sh \
  task=unified \
  task.benchmark=<Domain>/<Task> \
  task.runtime.use_conda_run=false \
  task.runtime.python_path=/mnt/shared-storage-user/p1-shared/luotianwei/Frontier-Engineering/.venv/bin/python
```

Do not overstate quality if either of these fails:

1. The benchmark cannot produce `valid=1` with a finite baseline score.
2. A 10-step `eval_single.sh` run produces only invalid candidates.
3. A 10-step run shows no meaningful improvement signal and you have not explicitly called that out as a remaining risk.

## Report With Decision Quality

When finishing the contribution, summarize:

1. Why this task was selected over alternatives.
2. Which repo path and integration mode were used.
3. What the authentic data source or canonical benchmark origin is.
4. What the editable agent surface is.
5. What baseline and evaluation metrics exist.
6. What remaining risks or environment gaps still exist.

If you reject a candidate, say why in concrete engineering terms such as weak source authenticity, redistribution ambiguity, dependency weight, nondeterminism, hidden data requirements, or excessive runtime.
