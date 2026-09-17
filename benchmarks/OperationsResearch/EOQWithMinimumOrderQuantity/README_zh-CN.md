# 带最小起订量的 EOQ

在冻结的确定性 EOQ 实例上选择订货量，并在存在硬性最小起订量时最小化平均年成本。

## 这个 Benchmark 在测什么

供应商 MOQ 是采购里非常常见的约束。它会直接影响营运资金占用和仓储压力，也经常把最优解从经典 EOQ 公式的内部点推到可行域边界上。

从算法角度看，这是一个建立在冻结解析成本模型上的小型约束优化问题。关键不在系统集成，而在于是否能正确处理边界和约束条件。

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
pip install -r benchmarks/OperationsResearch/EOQWithMinimumOrderQuantity/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/OperationsResearch/EOQWithMinimumOrderQuantity/verification/evaluator.py \
  benchmarks/OperationsResearch/EOQWithMinimumOrderQuantity/scripts/init.py \
  --metrics-out /tmp/EOQWithMinimumOrderQuantity_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/EOQWithMinimumOrderQuantity \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
