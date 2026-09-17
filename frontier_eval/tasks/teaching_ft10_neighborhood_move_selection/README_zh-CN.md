# FT10 邻域移动选择

这个教学版任务基于 `benchmarks/OperationsResearch/FT10NeighborhoodMoveSelection`。
它面向有 CS 背景、但还不熟悉作业车间调度的读者，用来解释一个经典的局部搜索优化问题。

## 目录结构

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

- `baseline/init.py`：一个只使用廉价局部特征的简单相邻交换排序策略。
- `verification/reference.py`：更强的参考实现，默认回放一个由 CP-SAT 导出的机器顺序；如果你设置 `TEACHING_FT10_ENABLE_ORTOOLS=1`，它也能尝试外部 OR-Tools 求解器。
- `verification/evaluate.py`：运行 baseline 和 reference，并按已知最优值 `930` 做归一化计分。

## 这个基准在教什么

这个任务要求你在一个冻结的局部搜索循环里，对机器顺序里的相邻交换动作排序。
你不是从头构造排程，而是决定“下一步先尝试哪个 swap”。

所以它很适合用来理解“在固定求解器壳层里做优化”这类问题：
模型、可行性检查和搜索循环都固定，变化的只有动作排序策略。

## 事实来源

冻结的 FT10 实例和所有运行时辅助函数都在：

`benchmarks/OperationsResearch/FT10NeighborhoodMoveSelection/runtime/problem.py`

<!-- AI_GENERATED -->
