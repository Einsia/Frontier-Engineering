# DuckDB 索引选择

在冻结的 DuckDB 分析 workload 上，从白名单中挑选一组索引，尽量降低总执行时间。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是稳定 DuckDB workload 上的物理设计调优。额外索引确实可能加速重复查询，但也会带来构建和维护成本，所以关键不是“建得越多越好”，而是选对那一小部分。

从计算角度看，这是一道固定候选集合上的子集选择题，而且分数来自真实执行时间，不是某个替代指标。

## 你真正会改的文件

- 目标文件：`scripts/init.py`
- 入口函数：`select_indexes(workload_manifest)`

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
pip install -r benchmarks/ComputerSystems/DuckDBIndexSelection/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/ComputerSystems/DuckDBIndexSelection/verification/evaluator.py \
  benchmarks/ComputerSystems/DuckDBIndexSelection/scripts/init.py \
  --metrics-out /tmp/DuckDBIndexSelection_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/DuckDBIndexSelection \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
