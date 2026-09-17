# 带障碍栅格路径规划

在冻结的二维占据栅格上规划一条无碰撞路径，并尽量降低路径代价。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是类似仓库巷道的单机器人导航场景。更短且合法的路径能直接减少周期时间、电量消耗和拥堵。

从计算角度看，它就是冻结栅格图上的搜索问题。图结构、合法性检查和代价函数都已经定义好，你只需要给出路径。

## 你真正会改的文件

- 目标文件：`scripts/init.py`
- 入口函数：`plan_path(grid, start, goal)`

## 先看哪里

- `Task_zh-CN.md`：中文任务契约与评分规则
- `Task.md`：英文任务说明
- `runtime/problem.py`：冻结实例、校验逻辑和指标辅助函数
- `baseline/solution.py`：基线实现
- `verification/evaluator.py`：本地评测入口
- `references/source_manifest.md`：来源与谱系说明

## 环境准备

从仓库根目录运行：

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/Robotics/GridPathPlanningWithObstacles/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/Robotics/GridPathPlanningWithObstacles/verification/evaluator.py \
  benchmarks/Robotics/GridPathPlanningWithObstacles/scripts/init.py \
  --metrics-out /tmp/GridPathPlanningWithObstacles_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Robotics/GridPathPlanningWithObstacles \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
