# FT10 Neighborhood Move Selection

This teaching scaffold is derived from `benchmarks/OperationsResearch/FT10NeighborhoodMoveSelection`.
It explains the local-search version of the classic FT10 job-shop benchmark for readers who know CS but do not know job-shop scheduling yet.

## Directory Structure

```text
teaching_ft10_neighborhood_move_selection/
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── baseline/
│   └── init.py
└── verification/
    ├── reference.py
    └── evaluate.py
```

- `baseline/init.py`: a simple adjacent-swap ranking policy that only uses cheap local cues.
- `verification/reference.py`: a stronger reference that replays a CP-SAT-derived machine order and can optionally rerun OR-Tools when `TEACHING_FT10_ENABLE_ORTOOLS=1`.
- `verification/evaluate.py`: runs baseline and reference, then normalizes the score against the known optimum `930`.

## What This Benchmark Teaches

The benchmark asks you to rank adjacent machine-order swaps inside a frozen local-search loop.
You do not build the schedule from scratch; instead, you guide which swap the search should try first.

That makes the task a good example of optimization inside an existing solver shell:
the physics, feasibility checks, and search loop are fixed, and only the move-ranking policy changes.

## Source of Truth

The frozen FT10 instance and all runtime helpers live in:

`benchmarks/OperationsResearch/FT10NeighborhoodMoveSelection/runtime/problem.py`

<!-- AI_GENERATED -->
