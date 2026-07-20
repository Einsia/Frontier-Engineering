# ProteinDesign - Protein Design

## Background

Protein design is a core problem in bioengineering: given a target structure (backbone), find the amino acid sequence that maximizes stability. This benchmark focuses on computation-driven protein sequence design optimization.

This domain task is based on "Protein Design with Agent Rosetta: A Case Study for Specialized Scientific Agents" (arXiv:2603.15952, ICML 2026), using PyRosetta (Rosetta's Python bindings) as the scoring engine.

## Tasks

| Task | Description |
|------|-------------|
| [FixedBackboneDesign](FixedBackboneDesign/Task.md) | Fixed-backbone protein sequence design optimization |

## Environment Setup

Tasks in this domain use the official Rosetta Docker image for evaluation to ensure environment consistency.

```bash
docker pull rosettacommons/rosetta:serial
```

Quick run command:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ProteinDesign/FixedBackboneDesign \
  task.runtime.isolation_mode=docker \
  task.runtime.docker_image=rosettacommons/rosetta:serial \
  algorithm=openevolve \
  algorithm.iterations=0
```
