# 燃油最小化船舶气象航线规划

在冻结的沿海栅格上规划船舶航线，在确定性的风场和流场影响下尽量降低燃油消耗。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是考虑天气影响的航线规划。一旦把逆风、侧风和流场影响都折算进燃油模型，几何最短路通常就不再是最省油的路线。

从算法角度看，它是在固定栅格图上的受约束路径规划问题，只不过边代价由环境场诱导出来。

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
pip install -r benchmarks/OperationsResearch/FuelMinimizingShipWeatherRouting/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/OperationsResearch/FuelMinimizingShipWeatherRouting/verification/evaluator.py \
  benchmarks/OperationsResearch/FuelMinimizingShipWeatherRouting/scripts/init.py \
  --metrics-out /tmp/FuelMinimizingShipWeatherRouting_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/FuelMinimizingShipWeatherRouting \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
