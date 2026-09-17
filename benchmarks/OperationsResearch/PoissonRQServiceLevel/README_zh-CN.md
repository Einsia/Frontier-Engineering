# 泊松需求 `(r,Q)` 服务水平约束

为冻结的泊松需求库存实例选择 `(r, Q)` 策略，并在满足硬性服务水平目标的前提下最小化平均成本。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是备件和 MRO 库存补货问题，需求以离散事件的形式到来，但仍然需要满足服务承诺。好的策略既要减少缺货，也不能在安全库存上花费过多。

它本质上是一个小型随机库存策略调优问题：评测器冻结了需求模型和成本核算，而你的代码只负责选择 `(r, Q)`。

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
pip install -r benchmarks/OperationsResearch/PoissonRQServiceLevel/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/OperationsResearch/PoissonRQServiceLevel/verification/evaluator.py \
  benchmarks/OperationsResearch/PoissonRQServiceLevel/scripts/init.py \
  --metrics-out /tmp/PoissonRQServiceLevel_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/PoissonRQServiceLevel \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
