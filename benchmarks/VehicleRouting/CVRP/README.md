# CVRP (Capacitated Vehicle Routing Problem) Benchmark

Standard CVRP: a fleet of identical vehicles serves all customers from a
single depot, each route within vehicle capacity, minimizing total distance.

## Structure

```
CVRP/
├── Task.md                  # Task description (rules, I/O contract, scoring)
├── baseline/
│   ├── solver.py            # Candidate solver (random-order cheapest insertion) + EVOLVE-BLOCK
│   └── result_log.txt       # Baseline evaluation log
├── verification/
│   ├── evaluator.py         # Runner + validator + scorer + candidate integrity checks (stdlib only)
│   ├── validator.py         # Candidate integrity validator (static checks + determinism probe)
│   ├── ref_solver.py        # Reference solver: deterministic GRASP multi-start + 2-opt + relocate/swap + 2-opt* + LNS
│   ├── generate_instances.py# Deterministic instance generator (seed 42, byte-stable; public + held-out)
│   ├── test_evaluator.py    # Unit tests: evaluator (stdlib unittest)
│   ├── test_validator.py    # Unit tests: validator
│   ├── test_ref_solver.py   # Unit tests: reference solver
│   ├── multiseed_stat.py    # Multi-seed baseline statistics script
│   └── requirements.txt
├── data/
│   ├── instances/           # 12 public TSPLIB-style .vrp instances (VRP-*)
│   ├── instances_heldout/   # 12 held-out instances (VHO-*), scored at evaluation time
│   └── reference.json       # Precomputed reference distance per instance (24)
└── frontier_eval/           # Unified-task metadata
```

## Requirements

Python 3 standard library only. No third-party dependencies.

## How to run

```bash
# Evaluate a candidate solver (inside the CVRP directory)
python verification/evaluator.py baseline/solver.py

# Unified-task adapter check (repo root)
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0
```

### Docker

The Dockerfile provides the evaluation environment (Python stdlib) for the
unified runtime's `isolation_mode=docker`. Build it and point the unified
runtime at it:

```bash
# Build the image (inside the CVRP directory)
docker build -t cvrp-benchmark -f verification/docker/Dockerfile .

# Use it from the repo root (see "Experiments" for the full command)
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0 task.runtime.isolation_mode=docker task.runtime.docker_image=cvrp-benchmark
```

> Docker isolation is validated on Linux / WSL. `frontier_eval/eval_command.txt`
> injects the host-benchmark path via the `{benchmark_source}` placeholder, so
> scoring works without framework changes; if the container user cannot write
> the evaluation sandbox, set `task.runtime.docker_user=<host uid>:<host gid>`
> (e.g. `1000:1000`). On Windows hosts the unified docker path is blocked by a
> framework path bug (`Path.resolve()` rewrites container paths to drive
> paths) — run docker mode under WSL instead.

The image intentionally contains no benchmark files (no `reference.json`, no
reference solver); the unified runtime mounts the sandbox into the container.

## Unified-task integration

- Benchmark id: `VehicleRouting/CVRP`
- The evaluator uses only the Python standard library, so no runtime overrides
  (`python_path`, conda env, or Docker image) are required; `eval_command.txt`
  uses plain `{python}`.
- Windows only: local validation must point `task.runtime.shell` at Git Bash
  (e.g. `task.runtime.shell=C:/Program Files/Git/bin/bash.exe`), because the
  default `bash` resolves to the WSL shim without `python` (returncode 127).
  Linux needs no override.

## Scoring

`score = min(100, 100 * reference_distance / candidate_distance)` averaged over
24 instances (12 public + 12 held-out). The reference distances are
precomputed by the deterministic `verification/ref_solver.py` and are
near-optimal (cross-checked against the archived best agent solver and an
OR-Tools GLS solve). Invalid solutions (missing/duplicate customers, capacity
violations, crashes, timeouts) score 0 and mark the run invalid. An optional
`CVRP_EVAL_SCORE_SCALE` knob (default 1.0) tightens the 100-point bar:
`score = min(100, scale * 100 * ref / cand)`.

## Reference scores (measured on this machine)

The current evaluation set is 24 instances (12 public + 12 held-out). Most
agent scores below were measured on the earlier 12-public-instance set (before
held-out instances were added) and are kept for cross-framework comparison;
fresh runs on the full 24-instance set (ShinkaEvolve 98.65, openevolve 98.00,
AB-MCTS 99.26) show the learned solvers generalize to unseen instances. See
"Experiments" for run records and multi-run statistics.

| Solver | combined_score |
|--------|----------------|
| baseline (random-order cheapest insertion), 24 instances | 54.69 |
| reference (deterministic GRASP + LNS, scoring baseline) | 100 (near-optimal) |
| agent (openevolve, 5 iterations, best, 12-instance set) | 96.38 |
| agent (openevolve, 5 iterations, best, **24-instance set**) | **98.00** |
| agent (ShinkaEvolve, 5 generations, best, 12-instance set) | 99.31 |
| agent (ShinkaEvolve, 5 generations, best, **24-instance set**) | **98.65** |
| agent (AB-MCTS, 5 candidates, best, 12-instance set) | 98.70 |
| agent (AB-MCTS, 5 candidates, best, **24-instance set**) | **99.26** |

Baseline score distribution over the 24 instances
(`python verification/evaluator.py baseline/solver.py`): mean **54.69**,
std 7.32, min 44.03 (`VHO-51-7`), max 71.55 (`VRP-21-3`). The solver is
deterministic (seeded RNG), so repeated runs are byte-identical; the spread
above is across instances, not across seeds.

**Multi-seed statistics** (reviewer-requested "multi-run statistics"):
`verification/multiseed_stat.py` derives fresh evaluation instance sets from
multiple seeds and computes each set's reference distances on the fly
(`python verification/multiseed_stat.py --seeds 111 222 333`):

| Seed | combined_score |
|------|----------------|
| 111  | 57.24 |
| 222  | 59.86 |
| 333  | 56.09 |
| **mean ± std** | **57.73 ± 1.58** (min 56.09, max 59.86) |

**Agent multi-run statistics** (3 runs per framework on the 24-instance set,
`deepseek-v4-flash`; full run IDs in "Experiments"):

| Framework | runs (combined_score) | mean | std | min | max |
|-----------|-----------------------|------|-----|-----|-----|
| openevolve (5 iterations) | 98.00, 97.96, 97.47 | **97.81** | 0.24 | 97.47 | 98.00 |
| ShinkaEvolve (5 generations) | 98.13, 54.69\*, 98.65 | **83.82** | 20.60 | 54.69 | 98.65 |
| AB-MCTS (5 candidates) | 98.49, 96.78, 99.26 | **98.18** | 1.04 | 96.78 | 99.26 |

\* one ShinkaEvolve run produced invalid programs in every generation (each
scored 0), so its best stayed at the baseline 54.69 — a genuine failure mode,
not an environment issue.

Agent scores are "best found" over stochastic evolution runs; multiple runs
are listed in the "Experiments" table where available (e.g. openevolve 96.38
and 95.65).

## Evaluation integrity

- **Held-out instances**: 12 `VHO-*` instances in `data/instances_heldout/`
  double the evaluation set to 24 and are scored alongside the public ones.
  Their `.vrp` files are **not** copied into the evaluation sandbox: the
  evaluator reads the paths from the host
  (`FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR`) and hands each to the
  candidate only while that instance is being scored. The files are public in
  the repo, and a running candidate receives the path and can read the file
  (see the threat model below); `Task.md` and `constraints.txt` tell the agent
  such held-out instances exist and will be scored, but their data is not
  available at code-generation time, so an LLM cannot hardcode routes by
  instance name. Per-instance name-keyed hardcoding is additionally rejected
  statically by `validator.py`, and `CVRP_EVAL_GENERATE_SEED` adds fresh
  instances at evaluation time so the scored set is not predictable.
- **Runtime-generated instances**: set `CVRP_EVAL_GENERATE_SEED` (and
  optionally `CVRP_EVAL_GENERATE_COUNT`, default 6) to additionally generate
  fresh instances at evaluation time from that seed. Each generated instance
  is scored against a reference computed on the fly by the reference solver,
  so a candidate cannot memorize the evaluation set even if it has seen every
  public instance file. Same seed ⇒ same instances ⇒ reproducible. Works in
  the direct evaluator and the unified runtime in process mode. In docker
  isolation mode (Linux / WSL) scoring works via the `{benchmark_source}` env
  injection in `eval_command.txt`, but runtime-generated instances are not
  available there because the unified runtime does not forward the seed env
  var into the container (framework-level limitation).
- **Sandbox**: `copy_files.txt` copies only `baseline/`, `data/instances/` and
  `frontier_eval/` into the evaluation sandbox (held-out instances and
  `reference.json` are read from the host, never copied).
  `frontier_eval/evaluator.py` is self-contained (parsing, validation,
  scoring and integrity checks are embedded), so no `verification/` files —
  including the reference solver — are copied. `reference.json` is never
  copied; the evaluator reads it from the host benchmark dir
  (`FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR`), and the candidate subprocess
  runs with **all `FRONTIER_*` variables removed** (plus reference/generation
  settings), so it cannot learn the host repo path — this closes the
  `FRONTIER_ENGINEERING_ROOT` side channel that would otherwise let a candidate
  find and import `verification/ref_solver.py` on the host.
- **Preflight checks** (`verification/validator.py`): the evaluator statically
  rejects candidates that modify code outside the EVOLVE-BLOCK, reference
  `verification` / `ref_solver` / `reference.json`, contain absolute paths, or
  hardcode per-instance routes; a determinism probe runs the candidate twice
  on small / medium / large probe instances and invalidates non-deterministic
  solvers.
- **Threat model**: all instance files (public and held-out) are visible in
  the repo and in the evaluation sandbox — a human who can read the repo could
  always hand-craft a solver, which no benchmark can prevent. The protections
  are deterrence-level: the constraints forbid reading the reference and
  hardcoding by instance name, `validator.py` statically rejects such
  attempts, and `CVRP_EVAL_GENERATE_SEED` makes the scored instance set
  unpredictable at evaluation time. The unified runtime (process and docker
  isolation) exposes the host repo to the candidate process (framework-level
  behavior shared by all tasks). Scoring only measures solution quality, never
  where the code came from.

## Experiments

All agent runs use the `deepseek-v4-flash` model. Scores are "best found";
LLM evolution is stochastic, so multiple runs are listed where available.

| Run | Framework | Score | Set |
|-----|-----------|-------|-----|
| baseline (random-order cheapest insertion) | — | 54.69 | 24 instances (12 public + 12 held-out) |
| reference (GRASP + LNS, scoring baseline) | — | 100 | 24 instances |
| `runs/.../openevolve/deepseek-v4-flash/20260807_170244` | openevolve, 5 iterations | 96.38 | 12 public |
| `runs/.../openevolve/deepseek-v4-flash/20260807_195321` | openevolve, 5 iterations | 95.65 | 12 public |
| `runs/.../openevolve/deepseek-v4-flash/20260811_215703` | openevolve, 5 iterations | 98.00 | 24 instances (12 public + 12 held-out) |
| `runs/.../openevolve/deepseek-v4-flash/20260812_172944` | openevolve, 5 iterations | 97.96 | 24 instances (12 public + 12 held-out) |
| `runs/.../openevolve/deepseek-v4-flash/20260812_174122` | openevolve, 5 iterations | 97.47 | 24 instances (12 public + 12 held-out) |
| `runs/.../shinkaevolve/deepseek-v4-flash/20260807_195503` | ShinkaEvolve, 5 generations | 99.31 | 12 public |
| `runs/.../shinkaevolve/deepseek-v4-flash/20260811_192446` | ShinkaEvolve, 5 generations | 98.13 | 24 instances (12 public + 12 held-out) |
| `runs/.../shinkaevolve/deepseek-v4-flash/20260812_175208` | ShinkaEvolve, 5 generations | 54.69\* | 24 instances (12 public + 12 held-out) |
| `runs/.../shinkaevolve/deepseek-v4-flash/20260812_175816` | ShinkaEvolve, 5 generations | 98.65 | 24 instances (12 public + 12 held-out) |
| `runs/.../abmcts/deepseek-v4-flash/20260807_190515` | AB-MCTS, 5 candidates | 98.70 | 12 public |
| `runs/.../abmcts/deepseek-v4-flash/20260812_102741` | AB-MCTS, 5 candidates | 98.49 | 24 instances (12 public + 12 held-out) |
| `runs/.../abmcts/deepseek-v4-flash/20260812_181308` | AB-MCTS, 5 candidates | 96.78 | 24 instances (12 public + 12 held-out) |
| `runs/.../abmcts/deepseek-v4-flash/20260812_182222` | AB-MCTS, 5 candidates | 99.26 | 24 instances (12 public + 12 held-out) |

Baseline reproduction:

```bash
# inside the CVRP directory
python verification/evaluator.py baseline/solver.py     # -> 54.69, valid 1.0 (24 instances)
python verification/test_evaluator.py                   # -> 23 unit tests pass
python verification/test_validator.py                   # -> 16 unit tests pass
python verification/test_ref_solver.py                  # -> 5 unit tests pass
python verification/test_frontier_eval_evaluator.py     # -> 6 unit tests pass (sandbox copy)
```

Unified adapter checks (repo root):

```bash
# process mode
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0

# docker isolation (build first: docker build -t cvrp-benchmark -f verification/docker/Dockerfile .)
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0 task.runtime.isolation_mode=docker task.runtime.docker_image=cvrp-benchmark
```
