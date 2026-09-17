# 动态流场最短航时船舶路径规划

在冻结的沿海栅格上规划船舶航线，利用确定性流场并满足最小水深约束，使总航时尽量短。

## 这个 Benchmark 在测什么

这个 benchmark 可以看作航道通行和港口进出规划的代理问题。更快的路线意味着更好的时刻可靠性，但一旦把流场增益和吃水限制考虑进去，几何最短路径往往既不合法，也不一定最快。

从算法角度看，它是在固定栅格图上的受约束最短路问题，只不过边代价会受到物理场影响。

## 你真正会改的文件

- 目标文件：`scripts/init.py`
- 入口函数：`solve(instance)`

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
pip install -r benchmarks/OperationsResearch/DynamicCurrentMinimumTimeRouting/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/OperationsResearch/DynamicCurrentMinimumTimeRouting/verification/evaluator.py \
  benchmarks/OperationsResearch/DynamicCurrentMinimumTimeRouting/scripts/init.py \
  --metrics-out /tmp/DynamicCurrentMinimumTimeRouting_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/DynamicCurrentMinimumTimeRouting \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
