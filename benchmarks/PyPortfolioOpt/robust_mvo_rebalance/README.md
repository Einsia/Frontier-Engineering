# Task 01: Robust Mean-Variance Rebalancing

This benchmark focuses on a realistic single-period portfolio rebalancing problem:
maximize risk-adjusted return under practical constraints (sector exposure, factor exposure,
weight bounds, and turnover limit), while paying transaction penalties.

## Why this task matters

A pure Markowitz optimizer is rarely deployable as-is. Real production systems must handle:
- exposure controls (sector constraints),
- style/risk controls (factor exposure constraints),
- implementation frictions (turnover and transaction costs),
- stable transitions from current holdings (`w_prev`) to new holdings (`w`).

This benchmark forces all of these constraints into one optimization problem.

## Environment Setup

Please install dependencies using the unified Task configuration:

```bash
pip install -r benchmarks/PyPortfolioOpt/requirements.txt
```

If you are running commands from this subfolder, use:

```bash
pip install -r ../requirements.txt
```

## Run

From repository root:

```bash
.venvs/frontier-v1-main/bin/python benchmarks/PyPortfolioOpt/robust_mvo_rebalance/verification/evaluate.py
```

Run with `frontier_eval` unified task:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=PyPortfolioOpt/robust_mvo_rebalance \
  task.runtime.env_name=frontier-v1-main \
  algorithm.iterations=0
```

Runtime note: the evaluator no longer solves the reference programs at scoring time (they are a frozen constant table), so a full run is dominated by the candidate itself and typically completes in a few seconds. The candidate gets a wall-clock budget of 240s across all 10 instances, overridable via `PYPFOPT_CANDIDATE_TIMEOUT_S`.

## Evaluation integrity

Two things this benchmark deliberately does:

- **The candidate runs in its own process.** `solve_instance(instance)` is
  invoked by a scorer-owned runner in a subprocess; only the solution vector
  crosses back. The evaluator recomputes the objective *and every constraint*
  itself, so nothing the candidate reports about its own score, penalty or
  validity is read, and the scorer's module globals are out of reach.
- **Feasibility is a hard gate, not a penalty.** Any constraint residual above
  the documented tolerance scores the instance 0 and marks the run invalid.
  There is no `(1 - penalty)` multiplier, so a portfolio that breaches a risk
  limit to buy objective is worth nothing rather than a few points less.

`verification/reference.py` is maintainer-only: it is not shown to the agent, not
copied into the sandbox, and never executed at scoring time. The reference
objective it produced is frozen into `verification/evaluate.py` as a constant
table (the evaluation seeds are fixed). Regenerate it with:

```bash
python verification/evaluate.py --regenerate-reference-table
```

## Directory Structure

```text
.
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── frontier_eval
│   ├── initial_program.txt
│   ├── candidate_destination.txt
│   ├── eval_command.txt
│   ├── agent_files.txt
│   ├── readonly_files.txt
│   ├── artifact_files.txt
│   └── constraints.txt
├── baseline
│   └── init.py
└── verification
    ├── reference.py
    └── evaluate.py
```
