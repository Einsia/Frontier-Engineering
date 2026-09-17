# FT10 派工规则优化

为经典 FT10 Fisher-Thompson 10x10 作业车间设计一个贪心派工规则，并最小化 makespan。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是车间里的在线派工问题。轻量级优先级规则今天仍然被广泛使用，因为它们部署简单，但对吞吐、延误和加班成本的影响却很大。

你并不是直接返回一份完整排程，而是在一个冻结调度器内部编写优先级函数，所以这个任务本质上是“固定模拟器里的策略设计”。

## 你真正会改的文件

- 目标文件：`scripts/init.py`
- 入口函数：`score_operation(operation, state)`

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
pip install -r benchmarks/OperationsResearch/FT10DispatchingRuleOptimization/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/OperationsResearch/FT10DispatchingRuleOptimization/verification/evaluator.py \
  benchmarks/OperationsResearch/FT10DispatchingRuleOptimization/scripts/init.py \
  --metrics-out /tmp/FT10DispatchingRuleOptimization_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/FT10DispatchingRuleOptimization \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
