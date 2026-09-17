# 悬臂梁柔顺度拓扑优化

在冻结的悬臂 pyMOTO 拓扑优化循环里更新密度场，并最小化最终柔顺度。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是轻量化支架和悬臂支撑结构设计问题。在固定材料预算下，目标是让悬臂结构尽可能刚。

从 CS 角度看，这不是一次性预测结果，而是在一个冻结的 FEM/SIMP 优化循环内部设计更新策略。

## 你真正会改的文件

- 目标文件：`scripts/init.py`
- 入口函数：`update_density(density, sensitivity, state)`

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
pip install -r benchmarks/StructuralOptimization/CantileverComplianceTopologyOptimization/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/StructuralOptimization/CantileverComplianceTopologyOptimization/verification/evaluator.py \
  benchmarks/StructuralOptimization/CantileverComplianceTopologyOptimization/scripts/init.py \
  --metrics-out /tmp/CantileverComplianceTopologyOptimization_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=StructuralOptimization/CantileverComplianceTopologyOptimization \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
