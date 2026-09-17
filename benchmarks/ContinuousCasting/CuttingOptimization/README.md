# CuttingOptimization: Continuous-Casting Cutting Optimization — offline/static (Frontier-Eng Benchmark)

An **original** Frontier-Engineering benchmark inspired by the CUMCM 2021 Problem D
(«连铸切割的在线优化»), formalized into a self-contained, deterministic optimization task.

A continuously cast steel billet is drawn at a fixed speed. Defects (crystalline-moulder
anomalies) create 0.8 m scrap segments inside the billet that must be cut out and scrapped.
A solver receives the billet length, the defect positions, and a customer target length with
an acceptance window, and must produce a **cutting plan** (a list of cut lengths that exactly
partition the whole billet) that minimizes the total scrapped length and then makes every
shipped piece as close to the target length as possible.

The full game rules and evaluation semantics are in [Task.md](./Task.md) (Chinese).

## Layout

```
benchmarks/ContinuousCasting/CuttingOptimization/
├── baseline/solver.py          # Candidate solver (EVOLVE-BLOCK region is the only editable part)
├── verification/
│   ├── generator.py            # Fixed-seed instance generator (defects + target window)
│   ├── simulator.py            # Scoring simulator (validate + scrap / penalty metric)
│   ├── evaluate.py             # Evaluation entry (subprocess + time budget + scoring)
│   ├── validator.py            # Integrity checks (static + env stripping + determinism)
│   ├── ref_solver.py           # Reference DP (1-D partition; documented "best" score)
│   ├── test_simulator.py       # Unit tests: simulator correctness
│   ├── test_generator.py       # Unit tests: deterministic / defect feasibility / headroom
│   ├── test_ref_solver.py      # Unit tests: reference-solver validity + optimality
│   ├── test_validator.py       # Unit tests: integrity checks / env stripping / determinism
│   ├── test_evaluator.py       # Unit tests: end-to-end evaluation behavior
│   ├── data/instances/         # 8 fixed instances (seed-fixed, reproducible)
│   ├── docker/Dockerfile       # Minimal stdlib-only python image
│   └── requirements.txt
├── frontier_eval/              # UnifiedTask metadata
├── Task.md                     # Task rules, interface, scoring, reference scores
└── README.md
```

## Requirements

- Python >= 3.10, standard library only (no third-party dependencies).
- Runtime is pure-Python; the reference DP and the baseline solver evaluate in well under a
  second per instance.

## Run

```powershell
# Score a solver on the fixed 8-instance set (default 60s time budget per instance)
python verification/evaluate.py baseline/solver.py

# Add runtime-generated instances (anti-hardcoding)
python verification/evaluate.py baseline/solver.py --generate-seed <SEED>

# Tighter budget (challenge tier: 10s)
python verification/evaluate.py baseline/solver.py --time-budget 10
```

### Docker

The evaluator is pure stdlib, so a minimal `python` image suffices. Build it and use the
unified runtime's `isolation_mode=docker`:

```bash
# Build (from the repo root)
docker build -t cutting-opt-benchmark -f benchmarks/ContinuousCasting/CuttingOptimization/verification/docker/Dockerfile benchmarks/ContinuousCasting/CuttingOptimization

# Score the baseline under docker isolation (WSL/Linux; Windows hosts are limited by a
# framework path bug). docker mode must NOT set task.runtime.shell; set DOCKER_USER so the
# container can write the WSL /tmp sandbox.
FRONTIER_EVAL_UNIFIED_DOCKER_USER=1000:1000 \
  .venvs/frontier-eval-driver-wsl/bin/python -m frontier_eval task=unified \
  task.benchmark=ContinuousCasting/CuttingOptimization algorithm=openevolve algorithm.iterations=0 \
  llm.timeout=600 task.runtime.isolation_mode=docker task.runtime.docker_image=cutting-opt-benchmark
```

**Verified (WSL, docker isolation)**: baseline `combined_score=72.49, valid=1.0, num_instances=8`
— identical to process mode. `docker` scoring works under WSL/Linux because `eval_command.txt`
injects `FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR={benchmark_source}`, which the container
resolves to the mounted repo path (no framework env-forwarding needed).

## Tests

```powershell
# From the task directory (stdlib unittest, no dependencies)
python -m unittest discover -s verification -p "test_*.py"
```

35 tests across six modules (simulator / generator / ref_solver / validator / evaluator /
sandbox evaluator):
piece-level scrap & penalty rules, feasibility checks (sum, length window, defect isolation),
determinism of generation and reference solver, reference-solver optimality vs the baseline,
validator integrity (EVOLVE-BLOCK / forbidden references / absolute paths / per-instance
hardcoding / env stripping / determinism probe), evaluator behavior (scoring, runtime
generation, cheating-candidate rejection), and the `frontier_eval/evaluator.py` sandbox entry
(consistency with `verification/evaluate.py` + cheat rejection). `verification/multiseed_stat.py`
computes multi-run mean ± std.

## Integrity / threat model

- **Runtime-generated instances**: with `CUTTING_EVAL_GENERATE_SEED` set, the evaluator
  generates fresh instances at evaluation time (temp dir, never in the repo/sandbox), so a
  candidate cannot pre-position solutions for them.
- **Candidate env stripping**: candidate subprocesses get `FRONTIER_*` / `CUTTING_EVAL_*`
  variables stripped (see `verification/validator.py`), closing the host-env side channel.
- **Static checks**: EVOLVE-BLOCK markers + fixed-region byte diff vs the initial baseline,
  forbidden imports of evaluation / generation / reference modules, absolute paths,
  per-instance hardcoding, plus a determinism probe (two runs must match). Any violation
  scores 0.
- **Sandbox scope**: the 8 fixed instances and the evaluator / validator sources are visible
  to the candidate during evolution (they are needed for scoring and `verification/simulator.py`
  is intentionally usable as a white-box scorer). Anti-hardcoding therefore relies on
  `CUTTING_EVAL_GENERATE_SEED` (fresh instances at evaluation time — set a seed, do not use a
  fixed one); the name-keyed hardcoding check is best-effort. `verification/ref_solver.py` and
  `verification/generator.py` are **not** copied into the sandbox and are additionally forbidden
  by the validator.
- Honest note: in process mode the candidate has host filesystem access (framework-wide
  limitation); this benchmark relies on the layered defenses above.

## Scoring

- Instances = 8 fixed (difficulties easy/medium/hard, S = 24..150 m, 0..6 defects, target
  window ±0.5 m around the customer target) + runtime-generated when `CUTTING_EVAL_GENERATE_SEED`
  is set.
- **Metric**: material utilization = `100 * (billet_length - (scrap + 1e-4*penalty)) / billet_length`,
  averaged over instances (0..100, higher is better). `scrap` = total scrapped length (defect
  pieces + sub-8.0 m pieces + over-window excess); `penalty = Σ|delivered − target|` over shipped
  pieces; the `1e-4` weight is so small that scrap strictly dominates, respecting the lexicographic
  objective of the original problem (the penalty only breaks ties among equal-scrap plans).
- Malformed output / out-of-range cuts / cuts that fail to isolate a defect / crash / timeout
  ⇒ 0 points for that instance.
- **Headroom guarantee**: the generator accepts only instances where the reference DP strictly
  beats a naive equal-split baseline by ≥ 0.1 m of scrap, so every instance has real
  optimization signal.
- Reference scores (verified on the fixed 8 instances, `verification/evaluate.py`):
  - baseline (equal-split, no target-awareness): **72.5** utilization (mean scrap 25.2 m)
  - reference DP (`verification/ref_solver.py`, 1-D partition): **88.7** utilization (mean scrap 10.6 m)
  - per-instance reference utilization: 95.8 / 88.8 / 91.8 / 75.2 / 92.4 / 87.0 / 89.4 / 89.3
  - agent (openevolve, 10 generations, best saved program): **88.7** utilization
    (run `20260903_130517`) — **equals the reference DP exactly**.
  - agent (ShinkaEvolve, 15 generations, via reasoning proxy): **88.4** utilization
    (near the optimum, run `20260904_182017`).
  - agent (AB-MCTS, 15 iterations): **72.5** utilization (= baseline; this run did not improve —
    AB-MCTS is weaker here, and low-reasoning mutations mostly regressed/invalidated).
  - honest design note: the offline optimum is **reachable** (a strong agent can derive the
    1-D partition DP and hit ~88.7 = the ceiling). So the offline task's difficulty is *deriving*
    the DP, not long-horizon search. The harder **online** companion
    ([CuttingOptimizationOnline](../CuttingOptimizationOnline/README.md)) is where info
    asymmetry keeps agents below the clairvoyant ceiling — see that README for the 3×2 matrix.
  - `verification/multiseed_stat.py` gathers multi-run mean ± std across framework run dirs.
