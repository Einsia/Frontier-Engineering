# Multi-Robot Prioritized Planning

This teaching scaffold is derived from `benchmarks/Robotics/MultiRobotPrioritizedPlanning`.
It explains small-scale multi-agent path finding for readers who know algorithms and graphs but are new to robotics path coordination.

## Directory Structure

```text
teaching_multi_robot_prioritized_planning/
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

## What This Benchmark Teaches

The benchmark asks you to plan collision-free paths for three robots on a frozen grid.
Each robot can move one cell per step or wait in place, and the hard part is preventing robots from colliding with each other while keeping the total path cost low.

This is a clean teaching example of prioritized planning:
choose an ordering of robots, plan one robot at a time in space-time, and reserve its path so later robots avoid it.

## Source of Truth

The frozen instance and runtime helpers live in:

`benchmarks/Robotics/MultiRobotPrioritizedPlanning/runtime/problem.py`

<!-- AI_GENERATED -->
