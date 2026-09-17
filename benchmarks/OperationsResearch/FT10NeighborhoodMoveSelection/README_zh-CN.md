# FT10 邻域移动选择

在经典 FT10 作业车间的冻结局部搜索壳层里，对相邻交换动作排序，并最小化 makespan。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是有限搜索预算下的排程改进问题。调度器已经有一个可行的当前解，真正重要的是它下一步优先尝试哪个邻域动作。

你控制的是固定局部搜索循环里的动作排序，而不是自己从头到尾搜索整个排程空间。

## 你真正会改的文件

- 目标文件：`scripts/init.py`
- 入口函数：`score_move(move, state)`

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
pip install -r benchmarks/OperationsResearch/FT10NeighborhoodMoveSelection/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/OperationsResearch/FT10NeighborhoodMoveSelection/verification/evaluator.py \
  benchmarks/OperationsResearch/FT10NeighborhoodMoveSelection/scripts/init.py \
  --metrics-out /tmp/FT10NeighborhoodMoveSelection_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/FT10NeighborhoodMoveSelection \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
