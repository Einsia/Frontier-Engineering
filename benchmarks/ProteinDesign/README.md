# ProteinDesign - Protein Design

## Background

Protein design is a core problem in bioengineering: given a target structure (backbone), find the amino acid sequence that maximizes stability. This benchmark focuses on computation-driven protein sequence design optimization.

This domain task is based on "Protein Design with Agent Rosetta: A Case Study for Specialized Scientific Agents" (arXiv:2603.15952, ICML 2026), using PyRosetta (Rosetta's Python bindings) as the scoring engine.

## Tasks

| Task | Description |
|------|-------------|
| [FixedBackboneDesign](FixedBackboneDesign/Task.md) | Fixed-backbone protein sequence design optimization |
| [NCAAInsertion](NCAAInsertion/Task.md) | Non-canonical amino acid (TRF) insertion design |

## Environment Setup

Tasks in this domain use the official Rosetta Docker image for evaluation to ensure environment consistency.

```bash
docker pull rosettacommons/rosetta:serial
```

Quick run commands:

```bash
# FixedBackboneDesign (Case A)
python -m frontier_eval \
  task=unified \
  task.benchmark=ProteinDesign/FixedBackboneDesign \
  task.runtime.isolation_mode=docker \
  task.runtime.docker_image=rosettacommons/rosetta:serial \
  algorithm=openevolve \
  algorithm.iterations=0

# NCAAInsertion (Case B)
python -m frontier_eval \
  task=unified \
  task.benchmark=ProteinDesign/NCAAInsertion \
  task.runtime.isolation_mode=docker \
  task.runtime.docker_image=rosettacommons/rosetta:serial \
  task.runtime.python_path=python3 \
  algorithm=openevolve \
  algorithm.iterations=0
```
