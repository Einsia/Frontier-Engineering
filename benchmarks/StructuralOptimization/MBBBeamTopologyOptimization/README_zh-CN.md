# MBB 梁拓扑优化

在冻结的半 MBB pyMOTO 拓扑优化循环里更新密度场，并最小化最终柔顺度。

## 这个 Benchmark 在测什么

半 MBB 梁是经典的“单位材料刚度最大化”基准。局部密度的小变化，可能帮助也可能破坏整体传力路径，所以更新规则必须具备超出单元局部邻域的判断能力。

这个任务依旧属于“冻结物理循环里的优化器设计”：你控制的是更新规则，而物理求解和可行性检查保持不变。

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
pip install -r benchmarks/StructuralOptimization/MBBBeamTopologyOptimization/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/StructuralOptimization/MBBBeamTopologyOptimization/verification/evaluator.py \
  benchmarks/StructuralOptimization/MBBBeamTopologyOptimization/scripts/init.py \
  --metrics-out /tmp/MBBBeamTopologyOptimization_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=StructuralOptimization/MBBBeamTopologyOptimization \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
