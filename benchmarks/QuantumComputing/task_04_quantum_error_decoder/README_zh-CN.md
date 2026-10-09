# 题目 04：量子纠错解码器

本题的导航文档。任务定义（目标、输入输出、评分）请看 [TASK_zh-CN.md](TASK_zh-CN.md)。

## 目标

解码一次旋转表面码 memory 实验：把 syndrome 批次和 graphlike detector error model 转成
逻辑观测量预测，并与最小权完美匹配（MWPM）比较。追平 MWPM 得 1.0，超过它大于 1.0，
无视 syndrome 得 0.0。

## 文件结构

- `baseline/solution.py`：agent evolve 入口。初始 baseline 永不预测翻转，按构造得 0.0 分。
  只有 `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END` 之间的区域可修改。
- `verification/evaluate.py`：评测入口。用 Stim 生成并采样各 regime，重算 MWPM anchor，
  在独立解释器中运行 candidate，并写出 `metrics.json`、`artifacts.json`、`eval_report.json`。
- `verification/candidate_runner.py`：加载 candidate 的隔离解释器。它只收到错误模型与
  syndrome，并拒绝 `stim`/`pymatching` 导入。
- `verification/requirements.txt`：评测端依赖（已固定版本）。
- `references/known_best.md`：实测 anchor 与标定点。
- `frontier_eval/`：unified task 元数据。
- `TASK.md`、`TASK_zh-CN.md`：任务契约（英文 / 中文）。

## 环境

解码器本身只需要 NumPy（允许使用 SciPy）。**评测器**需要 Stim 与 PyMatching，它们不在
框架默认运行时里：

```bash
pip install -r benchmarks/QuantumComputing/task_04_quantum_error_decoder/verification/requirements.txt
```

版本固定是有意为之。Stim 的带种子采样流在不同版本间并不稳定，换版本会让 trivial 与 MWPM
参考移动约 1–2% 的分数；且 Stim 1.13 只提供 CPython 3.8–3.12 的 wheel（3.13 需要
`stim>=1.15`）。`frontier-v1-main` 基于 Python 3.12，并已把本题的 requirements 文件列入
清单，因此标准 bootstrap 已经覆盖：

```bash
bash scripts/env/setup_v1_task_envs.sh
```

## 快速运行

在当前题目目录执行：

```bash
python verification/evaluate.py --candidate baseline/solution.py
```

可选参数：

- `--metrics-out <path>`：给 unified harness 的指标 JSON（默认 `metrics.json`）。
- `--artifacts-out <path>`：诊断信息 JSON（默认 `artifacts.json`）。
- `--report-out <path>`：完整可读报告（默认 `eval_report.json`）。

初始 baseline 会输出 `combined_score=0.0000 valid=1`。

## Unified 运行

在仓库根目录执行：

```bash
python -m frontier_eval task=unified \
  task.benchmark=QuantumComputing/task_04_quantum_error_decoder \
  task.runtime.python_path=uv-env:frontier-v1-main \
  algorithm=openevolve algorithm.iterations=0
```

## 密封评测

development 的随机种子是固定的，以便分数跨运行可比；这也意味着 candidate 可以针对这批
具体样本调参。若需要一次全新、不可预测的评测，可覆盖种子；anchor 会在新样本上重算，
因此归一化依然有效：

```bash
QEC_DEV_SEED=$RANDOM QEC_SEALED_SEED=$RANDOM \
  python verification/evaluate.py --candidate baseline/solution.py
```

`QEC_CANDIDATE_TIMEOUT_S`（默认 240）限制候选子进程的墙钟时间。

## 已知局限

一并写清楚，因为它们界定了这里分数的含义：

- **吞吐量也是分数的一部分。** candidate 在墙钟预算内运行。一个没有在 shot 维度向量化
  的正确解码器会超时并得 0 分，因此较慢的机器可能让同一个解码器少得分。
- **0 → 1 区间主要是复现。** 达到 1.0 意味着追平一个有充分文献记录的 baseline（MWPM）。
  只有高于 1.0 才代表前沿工作，且这类结果应在一批全新未固定种子的样本上复核。
- **跨平台漂移。** Stim 的带种子采样与匹配在不同架构上并非逐位一致，绝对错误率在机器间
  会有几个百分点的移动。分数仍然自洽，因为 anchor 在同一次运行、同一批 shot 上重算。
- **1.0 以上的区间是开放的。** 已知存在优于 MWPM 的解码器，但 candidate 无法像 MWPM
  anchor 那样与一个公开数值直接核对。