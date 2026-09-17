# 狭窄通道路径规划

在冻结的狭窄通道占据栅格上规划一条无碰撞路径，并尽量接近最优路径代价。

## 这个 Benchmark 在测什么

狭窄通道是规划算法的经典失效模式。一个在开阔空间里看起来很正常的规划器，到了门洞、单格走廊或其他瓶颈位置时，可能会明显失效。

它本质上还是图搜索，但拓扑结构会把可行路径强行压进一条很薄的通道里，所以很多局部上看着合理的启发式会浪费搜索，甚至试图走非法捷径。

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
pip install -r benchmarks/Robotics/NarrowPassagePlanning/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/Robotics/NarrowPassagePlanning/verification/evaluator.py \
  benchmarks/Robotics/NarrowPassagePlanning/scripts/init.py \
  --metrics-out /tmp/NarrowPassagePlanning_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Robotics/NarrowPassagePlanning \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
