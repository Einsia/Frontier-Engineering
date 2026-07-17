# Inventory-Aware Quoting

Design a deterministic policy that quotes the less-liquid DUAL listings of three synthetic
equities. The primary listing is a fair-value reference, while competitiveness against the DUAL
top of book determines execution. The policy must balance spread capture, adverse selection,
fees, changing liquidity, and inventory risk.

Each observation also contains compositional, natural-language desk mandates. A policy must branch
between liquidity support, adverse-selection defense, and inventory recovery; one static set of
numeric quote parameters is deliberately insufficient for feasibility.

Edit only the EVOLVE-BLOCK in `scripts/init.py` and keep
`decide_quotes(observation) -> dict` working.

## Setup

The task is offline and CPU-only. From this task directory:

```bash
python -m pip install -r verification/requirements.txt
```

No dataset, exchange connection, GPU, Docker image, or model API is required for baseline
evaluation. A direct run normally completes in under 20 seconds on a laptop.

## Direct evaluation

```bash
python verification/evaluator.py scripts/init.py \
  --metrics-out metrics.json --artifacts-out artifacts.json
```

## Regression tests

```bash
python -m unittest discover -s verification -p "test_*.py" -v
```

## Unified evaluation

From the repository root, use benchmark id
`MarketMaking/InventoryAwareQuoting`. The included task config makes it directly discoverable:

```bash
python -m frontier_eval task=inventory_aware_quoting \
  algorithm=openevolve algorithm.iterations=0
```

No task-specific runtime override is needed on the repository's supported Linux setup.
`metrics.json` contains the ranking score, continuous diagnostic score, and feasibility flag.
`artifacts.json` contains detailed feedback for 12 development regimes plus aggregate results for
8 deterministic validation regimes.

Candidate policies run in a separate worker process with bounded import, decision, and total
runtime. This prevents a candidate from mutating the parent evaluator or reading its live future
market tape; it is process isolation, not an operating-system security sandbox.

See `Task.md` for the exact observation/action schema, simulator, constraints, and score. See
`references/design_notes.md` for modelling choices, validation design, and limitations.
