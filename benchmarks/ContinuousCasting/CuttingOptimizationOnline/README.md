# CuttingOptimizationOnline: Online Optimization of Continuous-Casting Cutting (Frontier-Eng Benchmark)

An **original** Frontier-Engineering benchmark extending the offline
[CuttingOptimization](../CuttingOptimization/README.md) task with a genuinely **online**
(closed-loop) decision process, modeled on CUMCM 2021 Problem D.

A continuously cast steel billet is drawn past a cutter. **Crystallizer anomalies create
0.8 m scrap segments, but the agent is only told about a segment when it is within
`reveal_lead` metres of the cut line** (final config `reveal_lead = 10` → hidden anomalies;
`reveal_lead = 60` is the "faithful" setting where the agent sees all relevant defects). The agent is invoked
*once per cut decision* with the **current visible state only** — it never sees future
defects — and must choose the next cut length. At the end the plan is scored against the
**full hidden defect set**: any piece overlapping a scrap segment is contaminated and fully
scrapped.

The full rules and evaluation semantics are in [Task.md](./Task.md) (Chinese).

## Layout

```
benchmarks/ContinuousCasting/CuttingOptimizationOnline/
├── baseline/solver.py          # Agent solver: decide(state)->piece_length (EVOLVE-BLOCK editable)
├── verification/
│   ├── generator.py            # Seeded instance generator (HIDDEN anomaly schedule + reveal_lead)
│   ├── simulator.py            # Closed-loop simulator + contamination/scrap scoring
│   ├── evaluate.py             # Per-decision closed-loop evaluation entry
│   ├── validator.py            # Integrity checks (static + FRONTIER_* stripping + determinism)
│   ├── ref_solver.py           # Clairvoyant reference DP (sees all defects) — the ceiling
│   ├── multiseed_stat.py       # Multi-run mean±std tool
│   ├── test_simulator.py       # Unit tests: scoring / validity
│   ├── test_generator.py       # Unit tests: deterministic / hidden schedule / reveal_lead
│   ├── test_ref_solver.py      # Unit tests: reference validity + beats baseline
│   ├── test_validator.py       # Unit tests: static checks / env stripping
│   ├── test_evaluator.py       # Unit tests: closed-loop eval / cheat rejection / generation
│   ├── test_frontier_eval_evaluator.py  # Unit tests: sandbox evaluator entry
│   ├── data/instances/         # 8 fixed instances (seed-fixed)
│   ├── docker/Dockerfile       # Minimal stdlib-only image
│   └── requirements.txt
├── frontier_eval/              # UnifiedTask metadata (openai-compatible LLM)
├── Task.md                     # Formal model, interface, scoring, reference scores
└── README.md
```

## Requirements

- Python >= 3.10, standard library only. The benchmark itself needs no third-party deps.
- To *run the agent search* you also need the Frontier-Eng framework + an OpenAI-compatible
  LLM endpoint (this task uses `deepseek-v4-flash` through a local reasoning-control proxy).

## Run

```powershell
# Score the baseline solver on the fixed 8-instance set (per-decision closed loop)
python verification/evaluate.py baseline/solver.py --reveal-lead 10

# Add runtime-generated instances (anti-hardcoding)
$env:ONLINE_CUT_EVAL_GENERATE_SEED = "<SEED rank>"
python verification/evaluate.py baseline/solver.py

# Multi-run stats (mean ± std) across a framework run dir
# Multi-run stats — note the tool aggregates every run in the dir; point it at the full run dir
# (it defaults to the online clairvoyant reference 76.37), or pass a sub-glob to restrict.
python verification/multiseed_stat.py --runs-dir runs/unified__ContinuousCasting__CuttingOptimizationOnline/openevolve
```

### Using an OpenAI-compatible proxy (required for the agent search)

`deepseek-v4-flash` is a reasoning model that can exhaust the token budget and return empty
content unless reasoning is controlled. Two things are needed:

1. **Route the LLM through a proxy** that raises `max_tokens` and injects a low
   `reasoning_effort`, e.g. `PROXY_PORT=8765 REASONING_MODE=low MAX_TOKENS=32768 python deepseek_proxy.py`,
   then `OPENAI_API_BASE=http://127.0.0.1:8765/v1`.
2. **ShinkaEvolve in particular loads `.env` with `override=True`**, which clobbers
   `OPENAI_API_BASE` and makes it bypass the proxy. **Force it via the hydra override
   `llm.api_base=http://127.0.0.1:8765/v1`** (config value, not env). openevolve / abmcts
   read `OPENAI_API_BASE` directly and do not need this.

## Tests

```powershell
python -m unittest discover -s verification -p "test_*.py"
```

23 tests across simulator / generator / ref_solver / validator / evaluator / sandbox
evaluator: scoring & validity (contamination, short-tail-as-scrap), deterministic generation,
reference validity + beats-baseline, validator integrity (EVOLVE-BLOCK / forbidden refs /
absolute paths / `FRONTIER_*` stripping / determinism), closed-loop evaluation (cheating
candidate rejected, runtime generation), and sandbox-evaluator consistency.

## Integrity / threat model

- **The instance data (which embeds the full hidden defect schedule) is NOT copied into the
  sandbox.** `frontier_eval/copy_files.txt` excludes `verification/data/instances`; the
  evaluator loads the fixed instances from the host source benchmark dir
  (`FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR`), so a candidate can never read the hidden
  defects out of a data file (it only ever gets the visible `state`). This is the core
  anti-cheat for the online task.
- `verification/ref_solver.py` and `verification/generator.py` are **not** copied into the
  sandbox and are additionally forbidden by the validator (`ref_solver`, `generator`,
  `anomaly_seed` tokens).
- Candidate subprocesses get **all `FRONTIER_*`** and `ONLINE_CUT_EVAL_*` variables stripped
  (`validator.candidate_env`), closing the host-env side channel.
- **Runtime generation** (`ONLINE_CUT_EVAL_GENERATE_SEED`) produces fresh instances at eval
  time, so a candidate cannot pre-position answers. (A fixed seed is predictable if the
  generator is public; use a fresh seed per runner for true anti-fingerprinting.)
- Determinism probe: the closed loop is run twice on a probe instance; the cut sequences must
  match.
- Honest note: in process mode the candidate has host filesystem access (framework-wide
  limitation); this benchmark relies on the layered defenses above.

## Scoring

- **Metric**: material utilization `util = 100 * (S - scrap) / S` averaged over instances
  (0-100, higher better). `scrap` = contaminated pieces (any overlap with a defect → whole
  piece scrapped) + clean pieces < 8.0 m (fully scrapped) + clean pieces above `target_max`
  (excess scrapped), plus a tiny target-fit penalty (`1e-4 * Σ|delivered − target|`) to break
  ties.
- **Contamination is unavoidable**: the minimum cut is 4.8 m, so a 0.8 m defect can never be
  isolated; it always contaminates ≥ 4.8 m of product. This is the source of the
  "online difficulty" and the informative asymmetry.
- **Reference scores (fixed 8 instances)**: baseline (fixed-target greedy) = **52.4**;
  clairvoyant DP (`verification/ref_solver.py`, sees all defects) = **76.4**. The clairvoyant
  is the theoretical ceiling — **an online agent that cannot see the future cannot reach it**.

### Agent scores (final config: `reveal_lead = 10`; unified low reasoning, 15 generations each, 3 runs per framework)

| Framework | run #1 | run #2 | run #3 | mean ± std |
|---|---|---|---|---|
| openevolve | 69.48 | 70.10 | 70.10 | **69.89 ± 0.36** |
| shinkaevolve | 70.06 | 71.18 | 70.10 | **70.45 ± 0.64** |
| abmcts | 72.31 | 70.10 | 70.45 | **70.95 ± 1.19** |

All 9 runs combined: mean **70.43 ± 0.83**. Reference (clairvoyant, sees all defects) = **76.4**
(gap ≈ 6.0), baseline (fixed-target greedy) = **52.4**.

Observed: **every run is below the clairvoyant ceiling (76.4) and above baseline (52.4)** — i.e.
the hidden-anomaly info asymmetry genuinely keeps online agents from the full-information optimum,
consistently across all three frameworks. This is the **key difference vs the offline** task, where
openevolve reaches the (offline) optimal exactly. The per-framework spread is small
(std ≈ 0.4–1.2), so agent scores settle around the "safe short-cut" plateau (~70) that limits how
far an online agent can get without full foresight.

> Methodological note: "online agents do not reach the clairvoyant optimum" is an **empirical**
> observation (3 frameworks × 3 runs each are all below 76.4), not a proven structural lower bound.
> To establish it rigorously one would add an "online oracle" reference layer — the best strategy
> that uses only the revealed information (respecting `reveal_lead`) — and show agents fall below it.

> Honest note: agents improve in step-jumps (stuck at baseline for several generations, then a
> single mutation cracks ~70), not gradual climbing — consistent with a hard constraint where
> "get the strategy right once" beats incremental search. AB-MCTS's single high run (72.31) vs its
> std (1.19) reflects run-to-run variance, not a systematic advantage.

> Honest note: agents improve in step-jumps (stuck at baseline for several generations, then a
> single mutation cracks ~68-72), not gradual climbing — consistent with a hard constraint
> where "get the strategy right once" beats incremental search.

## Docker

A minimal `python:3.11-slim` image is provided (`verification/docker/Dockerfile`). Build it
and run the unified runtime in `isolation_mode=docker` (WSL/Linux; Windows hosts are limited
by a framework path bug). docker mode must NOT set `task.runtime.shell`; set
`FRONTIER_EVAL_UNIFIED_DOCKER_USER=1000:1000` so the container can write the WSL `/tmp`
sandbox:

```bash
docker build -t cutting-opt-online -f benchmarks/ContinuousCasting/CuttingOptimizationOnline/verification/docker/Dockerfile benchmarks/ContinuousCasting/CuttingOptimizationOnline
FRONTIER_EVAL_UNIFIED_DOCKER_USER=1000:1000 \
  .venvs/frontier-eval-driver-wsl/bin/python -m frontier_eval task=unified \
  task.benchmark=ContinuousCasting/CuttingOptimizationOnline algorithm=openevolve algorithm.iterations=0 \
  llm.timeout=600 task.runtime.isolation_mode=docker task.runtime.docker_image=cutting-opt-online
```

**Verified (WSL, docker isolation)**: baseline `combined_score=52.40, valid=1.0, num_instances=8`
— identical to process mode. This also confirms the online anti-cheat holds in docker: the fixed
instances (with the hidden defect schedule) are **not** copied into the sandbox; the evaluator
loads them from the host source benchmark dir (`{benchmark_source}` → the mounted repo path in the
container), so the candidate in the container never reads the hidden defects.
