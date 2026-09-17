# LA16 派工规则优化

为经典 LA16 Lawrence 10x10 作业车间设计一个贪心派工规则，并最小化 makespan。

## 这个 Benchmark 在测什么

这个 benchmark 和 FT10 的策略设计问题类似，但实例换成了经典的 LA16 瓶颈结构。即便只是局部评分函数的细小变化，也可能带来很大的吞吐差异。

你仍然是在一个冻结调度器内部编写局部优先级函数，而不是自己显式构造整份排程。

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
pip install -r benchmarks/OperationsResearch/LA16DispatchingRuleOptimization/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/OperationsResearch/LA16DispatchingRuleOptimization/verification/evaluator.py \
  benchmarks/OperationsResearch/LA16DispatchingRuleOptimization/scripts/init.py \
  --metrics-out /tmp/LA16DispatchingRuleOptimization_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/LA16DispatchingRuleOptimization \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
