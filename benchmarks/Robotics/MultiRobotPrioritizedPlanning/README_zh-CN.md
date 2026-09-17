# 多机器人优先级路径规划

在冻结的栅格地图上为 3 台机器人规划无碰撞路径，并尽量降低总路径代价。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是共享巷道里的小规模机器人协同规划。好的路径集合既要避免互相阻塞和死锁，也不能把总路程拉得太长。

从计算角度看，它是一个小规模 multi-agent path finding 问题。单机器人最短路不难，真正的难点是让多条路径同时避开顶点冲突和边交换冲突。

## 你真正会改的文件

- 目标文件：`scripts/init.py`
- 入口函数：`plan_paths(grid, starts, goals)`

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
pip install -r benchmarks/Robotics/MultiRobotPrioritizedPlanning/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/Robotics/MultiRobotPrioritizedPlanning/verification/evaluator.py \
  benchmarks/Robotics/MultiRobotPrioritizedPlanning/scripts/init.py \
  --metrics-out /tmp/MultiRobotPrioritizedPlanning_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Robotics/MultiRobotPrioritizedPlanning \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
