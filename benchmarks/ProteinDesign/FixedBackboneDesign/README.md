# FixedBackboneDesign

## Quick Start

```bash
cd benchmarks/ProteinDesign/FixedBackboneDesign
mkdir -p outputs
python verification/evaluator.py prepare --raw-task data/raw_task.json --prepared-output outputs/prepared.pdb
python scripts/init.py --prepared-input outputs/prepared.pdb --solution-output outputs/solution.pdb
python verification/evaluator.py evaluate --native outputs/prepared.pdb --candidate outputs/solution.pdb --result-output outputs/result.json
```

## Background

This task is inspired by Agent Rosetta (Teneggi et al., arXiv:2603.15952, ICML 2026), which demonstrates LLM-driven protein design using Rosetta. This benchmark adapts the fixed-backbone sequence design problem as a standalone engineering optimization task.

## Unified Benchmark ID

`ProteinDesign/FixedBackboneDesign`

## Environment

```bash
docker pull rosettacommons/rosetta:serial
```
