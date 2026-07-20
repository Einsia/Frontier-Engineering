# Frontier-Eng

[English](README.md) | 简体中文

[主页](https://lab.einsia.ai/frontier-eng/) · [arXiv](http://arxiv.org/abs/2604.12290) · [Discord](https://discord.gg/hxeVhZNN)

Frontier-Eng 是一个面向 **generative optimization** 的 benchmark：Agent 不是一次性写出“标准答案”，而是持续修改可运行的工程代码，读取只读 verifier 的反馈，并在固定预算内不断改进。

当前版本包含 **47 个任务**，覆盖计算系统、量子信息、运筹优化、机器人控制、光学通信、物理与工程设计。主页和论文的核心观点是：真实工程问题通常从一个可行 baseline 出发，价值来自持续优化，而不是 pass/fail。

## News

- **2026-06-30** — **新增评测指标：金银铜 Medal Score。** 在 average rank 之外，我们发布同侪相对的 *Medal Score*（归一化到 `[0,1]`）：每道题取 v1 snapshot 中最好的前三名分数冻结为金/银/铜 baseline，模型达到金/银/铜分别得 1.00 / 0.67 / 0.33，对题集求均值；同时汇报 v1（47 题）与 v1-lite（10 题）。它只奖励"达到该题最前沿（领奖台）"，忽略长尾里可忽略的微小差距，使跨题汇总更公平。每题 podium 分数与榜单见 [`leaderboard/`](leaderboard/README.md)。
- **2026-06-30** — **发布 `v1-lite`。** `v1` 的 10 题代表性子集，覆盖全部五大类、family 各不相同，专选"分数随预算逐步提升（而非一步做满或非高即低）"的题，配置见 `frontier_eval/conf/batch/v1_lite.yaml`。
- **2026-07-17** — **版本分支说明。** 过往论文版本已冻结为 `v1-arxiv` 分支，用于复现与对标基线；当前 `main` 作为新版本开发主线，欢迎大家持续在 `main` 提交贡献。

## 这个 benchmark 在测什么

和传统 agent benchmark 相比，Frontier-Eng 更关注三件事：

- 连续分数，而不是二值对错
- 真正的 verifier / simulator，而不是 judge model
- 在预算内能把 baseline 推到多远，而不是平均通过率


## 0. Host Requirements

仓库自带的 Python 环境可以自动化，但如果你要完整跑 `v1` baseline sweep，宿主机仍然默认需要具备下面这些条件：

| 条件 | 用途 | 说明 |
|---|---|---|
| 常规构建工具和可用外网 | 所有 setup 路径 | `uv`、Python wheel 和 benchmark-local 下载都会用到 |
| NVIDIA GPU + 可用 CUDA 栈 | `KernelEngineering/*`、`Aerodynamics/CarAerodynamicsSensing`、部分 Robotics 任务 | 纯 CPU 任务不需要 |
| Docker | `EngDesign` | 只有这一组任务依赖 |
| Octave | `Astrodynamics/MannedLunarLanding` | 属于 `uv` 不会安装的宿主机工具 |
| 额外数据 / checkpoint / 第三方仓库 | 如 `SustainableDataCenterControl`、`CarAerodynamicsSensing`、`MolecularMechanics` | 具体路径和准备方式见各任务 README |

如果你想看更具体的宿主机准备步骤，包括 `Docker` / `Octave` 怎么装、哪些外部资产要单独准备，请先读 [`run_zh-CN.md`](run_zh-CN.md)。

## 快速开始

### 1. 安装 `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

### 2. 创建 driver 环境

在仓库根目录执行：

```bash
bash init.sh
source .venvs/frontier-eval-driver/bin/activate
```

这里创建的是 **driver** 环境，只负责运行 `python -m frontier_eval`。

### 3. 先跑 smoke

```bash
python -m frontier_eval task=smoke algorithm=openevolve algorithm.iterations=0
```

这个命令不需要 LLM key，适合先确认框架本身没问题。

## 跑真实 benchmark

这个仓库的环境分两层：

- `frontier-eval-driver`：driver 环境
- `.venvs/<runtime-name>`：任务 runtime，比如 `frontier-v1-main`、`frontier-v1-kernel`、`frontier-v1-summit`

创建发布版 `v1` 题集使用的 task runtime：

```bash
bash scripts/env/setup_v1_task_envs.sh
```

现在 runtime 选择方式是：

- `task.runtime.env_name=<name>`：把 `.venvs/<name>/bin` 放到 `PATH` 前面
- `task.runtime.python_path=uv-env:<name>`：需要显式解释器路径的任务，直接解析到 `.venvs/<name>/bin/python`

### 单任务 baseline 验证

不需要 LLM key：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=WirelessChannelSimulation/HighReliableSimulation \
  algorithm=openevolve \
  algorithm.iterations=0
```

### 整套 `v1` baseline 验证

如果你想验证发布版 `v1` 题集的 baseline，而不是跑优化过程：

```bash
bash scripts/batch/validate_v1_task_envs.sh
```

它会按 `v1` 题集对应的 batch 配置把任务都以 `algorithm.iterations=0` 跑一遍，也就是只评估仓库自带 baseline，不会调用 LLM。

如果你后面要跑正常的优化实验，再看 [`run_zh-CN.md`](run_zh-CN.md)。

## 继续阅读

- 框架命令与 task onboarding：[`frontier_eval/README_zh-CN.md`](frontier_eval/README_zh-CN.md)
- `v1` 题集的批量运行说明：[`run_zh-CN.md`](run_zh-CN.md)
- 完整任务列表：[`TASK_DETAILS_zh-CN.md`](TASK_DETAILS_zh-CN.md)
- 历史实验最优代码存档：[`baseline_archive/README.md`](baseline_archive/README.md)

## Leaderboard

详细榜单（含 average rank）见 [lab.einsia.ai/frontier-eng/leaderboard](https://lab.einsia.ai/frontier-eng/leaderboard)。发布的分数表与每题金银铜 podium 见 [`leaderboard/`](leaderboard/README.md)。

**Medal Score**（金银铜 podium，越高越好，归一化到 `[0,1]`，即每题领奖台得分的均值）。每题取 **v1 snapshot (2026-04-14)** 的前三名分数冻结为金/银/铜 baseline，模型达到金/银/铜分别得 1.00 / 0.67 / 0.33。同时汇报 **v1**（47 题）与 **v1-lite**（10 题）两个集合；金银铜次数为 v1（`gpt-5.4` 采用其 47 题全量重测结果）：

| 排名 | Model | Medal (v1) | Medal (v1-lite) | 🥇 | 🥈 | 🥉 |
| :--: | :--- | --: | --: | --: | --: | --: |
| 1 | GPT-5.4 | 0.596 | 0.667 | 24 | 5 | 2 |
| 2 | Claude Opus 4.6 | 0.490 | 0.501 | 9 | 18 | 6 |
| 3 | GLM-5 | 0.312 | 0.233 | 4 | 10 | 12 |
| 4 | DeepSeek V3.2 | 0.248 | 0.166 | 3 | 9 | 8 |
| 5 | Gemini 3.1 Pro Preview | 0.213 | 0.200 | 3 | 6 | 9 |
| 6 | Seed 2.0 Pro | 0.185 | 0.100 | 3 | 7 | 3 |
| 7 | Grok 4.20 | 0.184 | 0.133 | 3 | 6 | 5 |
| 8 | Qwen3 Coder Next | 0.121 | 0.000 | 3 | 3 | 2 |

## 贡献

贡献指南见 [`CONTRIBUTING_zh-CN.md`](CONTRIBUTING_zh-CN.md)。
