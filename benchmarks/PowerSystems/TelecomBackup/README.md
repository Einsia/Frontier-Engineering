# TelecomBackup: Power-Backup Scheduling for Telecom Sites (Frontier-Eng Benchmark)

An **original** Frontier-Engineering benchmark: given a region of telecom sites powered by
batteries, a solver must produce a **time-sequenced on/off schedule for every power supply** that
maximizes the region's total backup time while keeping good LTE coverage (RSRP > -105 dBm) above
80% at every moment. The power-consumption parameters live in each instance and are calibrated so
that stagger/rotation scheduling has clear, reproducible headroom over the naive always-on strategy
(see "Scoring" and "Provenance / design rationale").

The full game rules and evaluation semantics are in [Task.md](./Task.md).

## Layout

```
benchmarks/PowerSystems/TelecomBackup/
├── baseline/solver.py          # Candidate solver (EVOLVE-BLOCK region is the only editable part)
├── verification/
│   ├── generator.py            # Fixed-seed instance generator
│   ├── simulator.py            # Scoring simulator (coverage/power/battery simulation)
│   ├── evaluate.py             # Evaluation entry (local / official modes, scoring)
│   ├── validator.py            # Integrity checks (static + env stripping + determinism)
│   ├── ref_solver.py           # Reference heuristic (rest-rotation) — documented "good" score
│   ├── test_simulator.py       # Unit tests: simulator correctness
│   ├── test_validator.py       # Unit tests: integrity checks / env stripping / determinism
│   ├── test_evaluator.py       # Unit tests: evaluation behavior, modes, reference path
│   ├── test_frontier_eval_evaluator.py  # Unit tests: sandbox path / official mode wiring
│   ├── data/instances/         # 8 fixed instances (seed-fixed, reproducible; local mode)
│   └── requirements.txt
├── frontier_eval/              # UnifiedTask metadata (ConnectFour/AntGame pattern)
├── Task.md                     # Task rules, interface, scoring, reference scores
└── README.md
```

## Requirements

- Python >= 3.10, standard library only (no third-party dependencies).
- Runtime is pure-Python simulation; each instance evaluation takes well under a second for
  the baseline solver.

## Evaluation modes

| Mode | Instance pool | Used by |
|---|---|---|
| `local` (default) | the 8 committed fixed instances | development / smoke tests |
| `official` (`TELECOM_EVAL_MODE=official`) | **only** freshly generated instances | the unified (`frontier_eval`) path |

In **official** mode the committed fixed instances are never scored, so a candidate cannot get
credit by memorising them. A generation seed (`TELECOM_EVAL_GENERATE_SEED`) is **mandatory**: if it
is missing the evaluator raises instead of silently falling back to the public instances.

## Run

```powershell
# local (development): the fixed 8 instances, default 60s budget per instance
python verification/evaluate.py baseline/solver.py --local

# local + runtime-generated instances (anti-hardcoding)
python verification/evaluate.py baseline/solver.py --local --generate-seed <SEED>

# official: generated instances only; the seed is mandatory
TELECOM_EVAL_MODE=official TELECOM_EVAL_GENERATE_SEED=<SEED> \
  python verification/evaluate.py baseline/solver.py

# tighter budget (challenge tier: 10s)
python verification/evaluate.py baseline/solver.py --local --time-budget 10
```

### Reproducing the reference score

The bundled reference heuristic is rejected by the candidate integrity checks (it has no
EVOLVE-BLOCK marker and contains a token the validator forbids), so scoring it uses the explicit
`--reference` bypass — it skips the candidate checks and exists **only** for reproducing the
documented reference score:

```powershell
python verification/evaluate.py verification/ref_solver.py --reference --local
# -> combined_score = 271.25, valid = 1.0  (the documented reference score)
```

### Docker

The evaluator is pure stdlib, so a minimal `python` image suffices. Build it and
use the unified runtime's `isolation_mode=docker`:

```bash
# Build (inside the TelecomBackup directory)
docker build -t telecombackup-benchmark -f verification/docker/Dockerfile .

# From the repo root
python -m frontier_eval task=unified task.benchmark=PowerSystems/TelecomBackup algorithm.iterations=0 \
  algorithm.evaluator.timeout=1200 \
  task.runtime.isolation_mode=docker task.runtime.docker_image=telecombackup-benchmark
```

> Docker isolation is validated on Linux / WSL. `frontier_eval/eval_command.txt`
> injects the host-benchmark path via the `{benchmark_source}` placeholder, so
> scoring works without framework changes; if the container user cannot write
> the evaluation sandbox, set `task.runtime.docker_user=<host uid>:<host gid>`
> (e.g. `1000:1000`). On Windows hosts the unified docker path is blocked by a
> framework path bug (`Path.resolve()` rewrites container paths to drive
> paths) — run docker mode under WSL instead.

## Tests

```powershell
# From the TelecomBackup task directory (stdlib unittest, no dependencies)
python -m unittest discover -s verification -p "test_*.py"
```

43 tests across four modules (simulator / validator / evaluator / sandbox wiring): simulator
correctness (manual golden cases, interval normalization, battery depletion, coverage constraint,
determinism); validator integrity (EVOLVE-BLOCK / forbidden references / absolute paths /
per-instance hardcoding / env stripping / determinism probe); evaluator behavior (scoring,
malformed/timeout/preflight handling, runtime generation, reproducibility, **official mode requires
a seed and excludes the public instances**, **`--reference` bypass**, **per-instance budget
self-limits to the framework timeout**); and the sandbox wiring (host-loaded generation, official
mode selected by `eval_command.txt`, the reference-solver cheat still rejected).

## Running inside the Frontier-Eng framework (official path)

`frontier_eval/eval_command.txt` sets `TELECOM_EVAL_MODE=official`, so the framework path always
scores freshly generated instances and **requires** the seed:

```powershell
# Windows: point the unified runtime at the venv python (WSL bash can't run Windows exes,
# so also use an MSYS2/Git bash instead of the default `bash`). Set PYTHONUTF8=1 to avoid
# GBK decoding crashes in some framework libs, and raise the LLM timeout for thinking models.
$env:PYTHONUTF8 = "1"
$env:FRONTIER_EVAL_UNIFIED_PYTHON = "<repo>\.venvs\frontier-eval-driver\Scripts\python.exe"
$env:TELECOM_EVAL_GENERATE_SEED = "<non-public SEED>"   # mandatory in official mode
python -m frontier_eval task=unified task.benchmark=PowerSystems/TelecomBackup algorithm.iterations=0 `
  algorithm.evaluator.timeout=1200 "task.runtime.shell=<path to Git Bash>" llm.timeout=300
```

**Pick a seed that is not committed to the repository.** The generator lives in this repo, so a
public, fixed seed would let someone with repo access precompute the generated instances and
hardcode their solutions — exactly the hole the official mode closes for the evolving agent. Use a
fresh seed per official run; the seed actually used is recorded in the metrics
(`generate_seed`) so any run can be replayed.

**Timeout.** The framework caps the whole evaluation with `FRONTIER_EVAL_EVALUATOR_TIMEOUT_S`
(the algorithm side defaults it to 300 s). An official run scores 8 generated instances plus a
cross-size determinism probe (3 instances run twice) = 14 solver runs, so the worst case is
`14 × 60 s = 840 s`, which exceeds 300 s — the official run must raise the cap (e.g.
`algorithm.evaluator.timeout=1200`, as above). If the observed cap is too small the evaluator
**shrinks the per-instance budget so the run still fits** (recording `budget_shrunk` and
`effective_time_budget_s`) rather than being killed mid-run.

## Time Budget Tiers (from the original problem)

| Tier | Budget | Notes |
|---|---|---|
| Base | 300 s | T+1: 10-min solve |
| Advanced (default) | 60 s | T+2: 1-min solve |
| Challenge | 10 s | T+3: 10-s solve |

Select a tier with `--time-budget <s>` (CLI) or `TELECOM_EVAL_TIME_BUDGET=<s>` (the framework
path reads this variable; the default is the 60 s advanced tier).

## Integrity / threat model

- **Official vs local scoring**: the official (framework) path scores *generated* instances only,
  so memorising the committed instances buys nothing; `local` mode exists for development and is
  explicitly not the official score.
- **Runtime-generated instances**: in official mode the evaluator generates fresh instances at
  evaluation time (into a temp dir, never written to the repo or the sandbox). A missing generation
  seed is a hard error, not a silent fall-back to the public instances.
- **Candidate env stripping**: candidate subprocesses get `FRONTIER_*` / `TELECOM_EVAL_*`
  variables stripped (see `verification/validator.py`), closing the host-env side channel.
- **Static checks**: EVOLVE-BLOCK markers + fixed-region byte diff vs the initial baseline,
  forbidden imports of evaluation/generation modules, absolute paths, per-instance hardcoding,
  plus a determinism probe (two runs must match). Any violation scores 0. `--reference` is the only
  way to skip these, and it is for the bundled reference solver, not for candidates.
- Honest note: in process mode the candidate has host filesystem access (framework-wide
  limitation); this benchmark relies on the layered defenses above. `verification/simulator.py`
  is intentionally exposed as a white-box scorer for candidate-side search.
- **Sandbox scope** (design trade-off): the 8 fixed instances and the evaluator/validator
  sources are visible to the candidate during evolution (they are needed for scoring and the
  simulator is intentionally usable); they are simply not scored in official mode. The name-keyed
  hardcoding check is best-effort (array-index dispatch can evade it, as in any static check). The
  reference solver (`ref_solver.py`) and the generator are **not** copied into the sandbox and are
  additionally forbidden by the validator.
- **Residual limitation**: this benchmark has no strong process-level isolation (a framework-wide
  limitation, see above) and no secret store, so it cannot defend against a repository-reading
  attacker who can run the generator offline for a *known* seed. The mitigation is procedural:
  the official seed is supplied per run and not committed (see "Running inside the framework").

## Scoring

- Instances: `local` mode = the 8 committed fixed instances (N = 20..40 sites, K = 6..12 power
  supplies, each instance carries its power-consumption params `p_silent` / `p_work_base` /
  `p_work_coef`); `official` mode = freshly generated instances only. Score = mean backup time
  (minutes).
- Malformed output / out-of-range intervals / crash / timeout ⇒ 0 points for that instance.
- **Power calibration**: instances are generated with `p_silent=0.05`, `p_work_base=3.0`,
  `p_work_coef=3.0` (silent is cheap, working is expensive), and the generator accepts only
  instances where a multi-rest stagger (rest 1..3 supplies at a time) beats "always-on" by ≥ 25%
  per instance, so the scheduling problem has large, reproducible headroom. Measured on the 8
  committed instances the acceptance headroom is **+27.9% .. +119.0%, mean +57.5%**.
  (This is *not* the same number as the reference solver's **+54%** over the baseline:
  271.25 / 176.25 − 1 = +53.9%. The two are easy to conflate; they measure different things.)
- Reference scores (deepseek-v4-flash agents; agent scores are **verified by directly evaluating
  the saved programs** from the task directory — candidate solvers resolve `verification/simulator.py`
  relative to their own location, so re-evaluating a saved program from an arbitrary path silently
  degrades it to the always-on fallback).
  - baseline (always-on, no scheduling): **176.2** minutes
  - reference heuristic (`verification/ref_solver.py`, multi-rest rotation): **271.2** minutes (+54%)
  - agent (openevolve, 25 iterations, best saved program): **414.4** minutes (+135%; run `20260816_130700`)
  - agent (ShinkaEvolve, 15 generations, best generation program): **312.5** minutes (+77%; run `20260816_214014`, gen 3)
  - agent (AB-MCTS, 15 iterations, best saved program): **266.9** minutes (+51%; run `20260816_220646`)
  - **multi-run statistics** (3 runs per framework, best valid saved program per run):
    - openevolve (25 iterations): 414.4 / 298.1 / 357.5 → **mean 356.7 ± 47.5**
    - ShinkaEvolve (15 generations): 312.5 / 357.5 / 325.6 → **mean 331.9 ± 18.9**
    - AB-MCTS (15 iterations): 266.9 / 208.8 / 227.5 → **mean 234.4 ± 24.2**
  - The numbers above are `local`-mode scores (the fixed 8 instances). Under **official** scoring
    the same saved programs also generalise to freshly generated instances, e.g. at seed 42
    (fixed 8 + 8 generated): openevolve **410.9**, ShinkaEvolve **319.4**, AB-MCTS **280.3**.
    Because official scoring uses a per-run (non-committed) seed, official scores are
    seed-dependent; the fixed-instance numbers are kept as the stable, reproducible reference.
  - horizon: 480 minutes (upper bound if coverage never fails)
  - note: with 5-15 iterations agents mostly plateau at the baseline; more iterations let all
    three frameworks discover stagger/coverage-driven schedules that beat it (openevolve even
    found a near-horizon minimal-covering-subset schedule, surpassing the reference heuristic).
    ShinkaEvolve's 25-generation run produced a higher-scoring but **non-deterministic** program
    (time-budgeted simulated annealing) that fails the determinism probe — only deterministic
    programs count (312.5 from the 15-generation run is the valid best).

## Provenance / design rationale

This is an original benchmark (no external dataset), so the parameter values are documented here
rather than cited. The region models a small urban district and the parameters are
engineering-plausible magnitudes chosen to give a **clear, reproducible** gap between naive and
scheduled operation:

- **Region 200 m × 200 m, 20 × 20 grid**: a neighbourhood-sized area, small enough that the
  pure-Python simulator stays fast, large enough that several sites are needed for coverage.
- **Path loss `P = pt_dbm − 10·n_exp·log10(d + 1)`**, `pt_dbm=20`, `n_exp=6`: a log-distance model;
  with these values a site's "good coverage" radius is roughly 120 m, so a 200 m district requires
  multiple cooperating sites.
- **RSRP threshold −105 dBm**: LTE RSRP above ≈ −105 dBm is commonly treated as "good" coverage
  (cell edge is usually around −110 dBm); we adopt −105 dBm as the "good cell" bar.
- **`coverage_ratio = 0.8`**: 80% of grid cells must be good at every instant. Deliberately below
  100% so the coverage constraint is *redundant* — supplies can take turns resting without
  breaching it. This redundancy is what creates the scheduling problem.
- **Power model `p_silent` vs `p_work_base + p_work_coef·load`**: `p_silent=0.05` kW (idling a
  supply is cheap) versus `p_work_base=3.0`, `p_work_coef=3.0` kW (working is expensive). This
  ratio is the whole point: it makes resting some supplies at any moment worth more than running
  everything. It was calibrated empirically — an earlier setting with a high silent drain made
  always-on close to optimal and the task had no headroom.
- **Battery 15–30 kWh, `site_cap=60`, `delta_min=5 min`, `horizon=96`** (8 h planning period):
  engineering-plausible sizes for a district backup system over an extended outage.

The generator (`verification/generator.py`) additionally rejects any instance where the best
stagger does not beat always-on by ≥ 25%, so every scored instance provably rewards scheduling.
