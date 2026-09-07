# 任务 01：鲁棒均值方差再平衡

该基准聚焦于一个贴近实盘的单期组合再平衡问题：
在行业暴露、因子暴露、仓位边界、换手率上限等约束下，最大化风险调整收益，同时考虑交易惩罚。

## 这个任务为什么重要

经典 Markowitz 结果通常不能直接下单，工程落地时必须处理：
- 暴露控制（行业约束）；
- 风险风格控制（因子暴露约束）；
- 实施摩擦（换手约束与交易惩罚）；
- 从当前持仓 `w_prev` 平滑过渡到新持仓 `w`。

这个基准把这些约束统一到一个优化问题里。

## 环境配置

请按统一依赖配置安装环境：

```bash
pip install -r benchmarks/PyPortfolioOpt/requirements.txt
```

如果你在当前子目录执行命令，可使用：

```bash
pip install -r ../requirements.txt
```

## 运行方式

在仓库根目录执行：

```bash
.venvs/frontier-v1-main/bin/python benchmarks/PyPortfolioOpt/robust_mvo_rebalance/verification/evaluate.py
```

使用 `frontier_eval` unified 任务运行：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=PyPortfolioOpt/robust_mvo_rebalance \
  task.runtime.env_name=frontier-v1-main \
  algorithm.iterations=0
```

耗时说明：评测时不再求解参考程序（参考值已固化为常量表），整轮耗时主要取决于候选本身，通常几秒即可完成。候选在 10 个实例上的总墙钟预算为 240 秒，可通过 `PYPFOPT_CANDIDATE_TIMEOUT_S` 覆盖。

## 评测完整性

本 benchmark 有两处刻意的设计：

- **候选在独立进程中运行**：`solve_instance(instance)` 由评测端自有的 runner 在子进程中
  调用，只有解向量会回传。目标值与**全部约束**都由评测端重算，因此候选自报的分数、罚项、
  有效性字段一概不采信，评测脚本的模块全局变量也不在候选可达范围内。
- **可行性是硬门槛，不是罚项**：任一约束残差超过文档中的容差，该实例直接记 0 分并将整次
  运行标记为 invalid。不再有 `(1 - penalty)` 乘子，所以靠突破风险限额换取目标值不会
  只损失几分，而是一分不得。

`verification/reference.py` 仅供维护者使用：不展示给 agent、不复制进沙箱、评测时也不执行。
它算出的参考目标值已固化为 `verification/evaluate.py` 中的常量表（评测随机种子固定）。
需要重算时执行：

```bash
python verification/evaluate.py --regenerate-reference-table
```

## 目录结构

```text
.
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── frontier_eval
│   ├── initial_program.txt
│   ├── candidate_destination.txt
│   ├── eval_command.txt
│   ├── agent_files.txt
│   ├── readonly_files.txt
│   ├── artifact_files.txt
│   └── constraints.txt
├── baseline
│   └── init.py
└── verification
    ├── reference.py
    └── evaluate.py
```
