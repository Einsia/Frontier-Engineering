# 正态需求 `(r,Q)` 95% 服务水平约束

为冻结的正态需求库存实例选择 `(r, Q)` 策略，并在满足硬性 95% 服务水平目标的前提下最小化平均成本。

## 这个 Benchmark 在测什么

这个 benchmark 对应的是在服务水平边界附近做库存策略调优。补货点的微小变化，就可能在 95% 左右这个固定目标附近明显改变缺货风险和资金占用。

从算法角度看，它是一个建立在冻结概率模型上的小型离散约束优化问题。

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
pip install -r benchmarks/OperationsResearch/NormalRQServiceLevel95/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/OperationsResearch/NormalRQServiceLevel95/verification/evaluator.py \
  benchmarks/OperationsResearch/NormalRQServiceLevel95/scripts/init.py \
  --metrics-out /tmp/NormalRQServiceLevel95_metrics.json
```

## 可选：使用 `frontier_eval`

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=OperationsResearch/NormalRQServiceLevel95 \
  algorithm.iterations=0
```

如果需要指定解释器，可以额外添加 `task.runtime.use_conda_run=false task.runtime.python_path=/path/to/python`。

<!-- AI_GENERATED -->
