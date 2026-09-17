# 增量折扣 EOQ

在冻结的 EOQ 实例上选择订货量，并在存在增量折扣时最小化平均年成本。

## 这个 Benchmark 在测什么

增量折扣合同在工业采购里很常见：只有超过各个断点的那部分单位，才会按更低单价计费。要得到好的订货量，不仅要选对 `Q`，还要正确处理分层累积的采购成本。

从 CS 角度看，这仍然是一个小型冻结搜索问题，只不过成本核算不是简单地查价格区间，而是要沿各个折扣层逐段累积。

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
pip install -r benchmarks/OperationsResearch/EOQWithIncrementalDiscounts/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/OperationsResearch/EOQWithIncrementalDiscounts/verification/evaluator.py \
  benchmarks/OperationsResearch/EOQWithIncrementalDiscounts/scripts/init.py \
  --metrics-out /tmp/EOQWithIncrementalDiscounts_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/EOQWithIncrementalDiscounts \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
