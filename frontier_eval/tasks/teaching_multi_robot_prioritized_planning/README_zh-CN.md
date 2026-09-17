# 多机器人优先级路径规划

这个教学版任务基于 `benchmarks/Robotics/MultiRobotPrioritizedPlanning`。
它面向懂算法和图搜索、但还没有接触过机器人协同规划的读者。

## 目录结构

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

## 这个基准在教什么

这个任务要求你在一张冻结栅格图上，为 3 台机器人同时规划无碰撞路径。
每台机器人每一步可以走到相邻格点，也可以原地等待，真正的难点是避免机器人之间的顶点冲突和边交换冲突，同时尽量降低总路径代价。

它很适合讲解 prioritized planning：
先决定机器人顺序，再用 space-time 搜索逐个规划，后面的机器人必须避开前面机器人已经占用的时间和空间。

## 事实来源

冻结实例和运行时辅助函数都在：

`benchmarks/Robotics/MultiRobotPrioritizedPlanning/runtime/problem.py`

<!-- AI_GENERATED -->
