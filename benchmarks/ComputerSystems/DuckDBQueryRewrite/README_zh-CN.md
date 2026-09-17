# DuckDB 查询重写

重写一条冻结的 DuckDB 分析 SQL，在保证结果完全一致的前提下尽量缩短运行时间。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是真实 SQL 调优场景：工程师往往不能改上游产品逻辑，但仍然可以通过重写一条慢查询来提速。这里性能当然重要，但前提永远是语义必须完全不变。

从计算机视角看，这是一道保持语义不变的程序变换题，只不过这里被优化的“程序”是 SQL。

## 你真正会改的文件

- 目标文件：`scripts/init.py`
- 入口函数：`rewrite_query(sql, workload_manifest)`

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
pip install -r benchmarks/ComputerSystems/DuckDBQueryRewrite/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/ComputerSystems/DuckDBQueryRewrite/verification/evaluator.py \
  benchmarks/ComputerSystems/DuckDBQueryRewrite/scripts/init.py \
  --metrics-out /tmp/DuckDBQueryRewrite_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/DuckDBQueryRewrite \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
