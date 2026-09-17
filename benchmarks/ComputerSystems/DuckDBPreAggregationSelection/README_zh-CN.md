# DuckDB 预聚合选择

在冻结的 DuckDB 报表 workload 上，从白名单中选择一组预聚合表，尽量降低总执行时间。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是数据仓库里很常见的一类决策：面对重复报表 workload，到底哪些汇总表值得物化。选错了会浪费存储和刷新成本，选对了才能真正降低重复扫描与聚合开销。

从算法角度看，它是固定候选集合上的物化视图选择题，而且分数来自真实查询执行，同时要满足严格结果一致性。

## 你真正会改的文件

- 目标文件：`scripts/init.py`
- 入口函数：`select_preaggregations(workload_manifest)`

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
pip install -r benchmarks/ComputerSystems/DuckDBPreAggregationSelection/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/ComputerSystems/DuckDBPreAggregationSelection/verification/evaluator.py \
  benchmarks/ComputerSystems/DuckDBPreAggregationSelection/scripts/init.py \
  --metrics-out /tmp/DuckDBPreAggregationSelection_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/DuckDBPreAggregationSelection \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
