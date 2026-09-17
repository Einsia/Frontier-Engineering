# 全量折扣 EOQ

在冻结的 EOQ 实例上选择订货量，并在存在全量折扣时最小化平均年成本。

## 这个 Benchmark 在测什么

全量折扣在包装、化工和合同制造里很常见。一旦跨过价格断点，订单里的每一个单位都会按更低单价计费，所以选错价格区间会显著拉高年度支出。

从算法角度看，这是一个带分段切换的冻结优化问题。输出仍然只是一个标量 `Q`，但目标函数会在价格区间切换时出现不连续变化。

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
pip install -r benchmarks/OperationsResearch/EOQWithAllUnitsDiscounts/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/OperationsResearch/EOQWithAllUnitsDiscounts/verification/evaluator.py \
  benchmarks/OperationsResearch/EOQWithAllUnitsDiscounts/scripts/init.py \
  --metrics-out /tmp/EOQWithAllUnitsDiscounts_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/EOQWithAllUnitsDiscounts \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
