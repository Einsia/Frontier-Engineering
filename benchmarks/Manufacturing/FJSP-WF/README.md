# FJSP-WF: Flexible Job Shop Scheduling with Worker Flexibility

## Engineering Background

FJSP-WF addresses a core challenge in manufacturing production scheduling: how to assign operations to machines and workers to minimize total production completion time (makespan), accounting for different worker skill levels.

This benchmark is based on the **official GECCO 2026 FJSSP-WU Competition** dataset ([Apache-2.0](https://github.com/jrc-rodec/FJSSP-W-Competition)), which provides 30 standardized instances with native worker flexibility data derived from classical FJSP benchmarks (Brandimarte, Hurink, Kacem, and others).

**What this benchmark evaluates:**
- Whether an AI agent can improve an existing scheduling algorithm through iterative code evolution
- The agent reads `scripts/init.py`, understands the problem, modifies the code, and receives quantitative feedback from the evaluator

## Benchmark Structure

| Path | Role |
|------|------|
| `scripts/init.py` | **Agent-editable artifact** — only file the agent can modify |
| `baseline/solution.py` | **Read-only baseline** — fixed reference for relative scoring |
| `verification/evaluator.py` | **Read-only evaluator** — parses `.fjs`/`.fjswf` instances, validates, and scores |
| `Task.md` | Full task specification, I/O spec, scoring rules |
| `data/instances/official/` | 30 official GECCO FJSSP-WU instances (`.fjs`, included as-is) |
| `data/instances/synthetic/` | 3 synthetic instances for CI smoke testing only (`.fjswf`) |
| `frontier_eval/` | Unified task metadata for the Frontier-Eval framework |

## Quick Start

Evaluate the solver on a synthetic instance (CI smoke test):
```bash
python verification/evaluator.py scripts/init.py --instances synthetic_01
```

Evaluate on an official competition instance:
```bash
python verification/evaluator.py scripts/init.py --instances mk07
```

Evaluate on multiple instances:
```bash
python verification/evaluator.py scripts/init.py --instances mk07 hs01 kc03
```

Run via Frontier-Eval framework (from repo root):
```bash
python -m frontier_eval task=unified task.benchmark=Manufacturing/FJSP-WF algorithm=openevolve algorithm.iterations=0
```

## Data

- **30 official instances** in `data/instances/official/` (`.fjs` format, from the GECCO FJSSP-WU Competition, Apache-2.0)
- **3 synthetic instances** in `data/instances/synthetic/` (`.fjswf` format, CI smoke testing only)

See `data/sources.md` for detailed provenance and attribution.

## Benchmark ID

`Manufacturing/FJSP-WF`