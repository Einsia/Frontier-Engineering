# CVRP（容量约束车辆路径问题）Benchmark

标准 CVRP：一支同型车队从单一仓库出发服务所有客户，每条路线不超过车辆容量，目标是最小化总行驶距离。

## 目录结构

```
CVRP/
├── Task.md                  # 任务说明（规则、输入输出契约、评分）
├── baseline/
│   ├── solver.py            # 候选求解器（随机顺序最近插入）+ EVOLVE-BLOCK
│   └── result_log.txt       # baseline 评测日志
├── verification/
│   ├── evaluator.py         # 运行器 + 验证器 + 评分器 + 候选完整性检查（仅标准库）
│   ├── validator.py         # 候选完整性验证器（静态检查 + 确定性探针）
│   ├── ref_solver.py        # 参考求解器：确定性 GRASP 多起点 + 2-opt + relocate/swap + 2-opt* + LNS
│   ├── generate_instances.py# 确定性实例生成器（seed 42，逐字节稳定；公开 + held-out）
│   ├── test_evaluator.py    # 单元测试：评测器（stdlib unittest）
│   ├── test_validator.py    # 单元测试：验证器
│   ├── test_ref_solver.py   # 单元测试：参考求解器
│   ├── multiseed_stat.py    # baseline 多 seed 统计脚本
│   ├── requirements.txt
│   └── docker/
│       └── Dockerfile       # 容器化评测环境（Docker 优先）
├── data/
│   ├── instances/           # 12 个公开 TSPLIB 风格 .vrp 实例（VRP-*）
│   ├── instances_heldout/   # 12 个 held-out 实例（VHO-*），评测时评分
│   └── reference.json       # 每个实例的参考距离（24 个，评分基准）
└── frontier_eval/           # Unified-task 元数据
```

## 依赖

仅需 Python 标准库，无第三方依赖。

## 如何运行

```bash
# 评测一个候选求解器（在 CVRP 目录下）
python verification/evaluator.py baseline/solver.py

# 框架适配验证（仓库根目录）
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0
```

### Docker

Dockerfile 为 unified 运行时的 `isolation_mode=docker` 提供评测环境（Python 标准库）。构建镜像并让 unified 运行时指向它：

```bash
# 构建镜像（在 CVRP 目录下）
docker build -t cvrp-benchmark -f verification/docker/Dockerfile .

# 从仓库根目录使用（完整命令见"实验记录"）
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0 task.runtime.isolation_mode=docker task.runtime.docker_image=cvrp-benchmark
```

> Docker 隔离在 **Linux / WSL** 下已验证可用。`frontier_eval/eval_command.txt` 通过 `{benchmark_source}` 占位符把宿主 benchmark 路径注入评测命令，评分无需改框架即可工作；若容器用户无法写入评测沙箱，设置 `task.runtime.docker_user=<宿主 uid>:<宿主 gid>`（如 `1000:1000`）。Windows 宿主的 unified docker 路径被框架的路径 bug 卡住（`Path.resolve()` 会把容器路径改写为盘符路径）——请在 WSL 下运行 docker 模式。

镜像内**刻意不包含任何 benchmark 文件**（没有 `reference.json`、没有参考求解器）；unified 运行时会把沙箱挂载进容器。

## 评分

`score = min(100, 100 × reference_distance / candidate_distance)`，跨 **24 个实例**（12 公开 + 12 held-out）取平均。
参考距离由确定性的 `verification/ref_solver.py` 预计算，为近最优（与存档最优 agent 解、OR-Tools GLS 交叉验证一致）。
非法解（客户缺失/重复、超容量、崩溃、超时）得 0 分，并使整个运行判无效（valid=0）。
可选评分旋钮 `CVRP_EVAL_SCORE_SCALE`（默认 1.0）可收紧 100 分线：`score = min(100, scale × 100 × ref / cand)`。

## 参考分数（本机实测）

当前评测集为 24 个实例（12 公开 + 12 held-out）。下面多数 agent 分数是在较早的 12 公开实例集上测得的（held-out 实例为后加），保留用于跨框架对比；在完整 24 实例集上的新运行（ShinkaEvolve 98.65、openevolve 98.00、AB-MCTS 99.26）证明学到的求解器能泛化到未见过的实例。运行记录与多运行统计见"实验记录"。

| 求解器 | combined_score |
|--------|----------------|
| baseline（随机顺序最近插入），24 实例 | **54.69** |
| reference（确定性 GRASP + LNS，评分基准） | 100（近最优） |
| agent（openevolve，5 轮，best，12 实例集） | 96.38 |
| agent（openevolve，5 轮，best，**24 实例集**） | **98.00** |
| agent（ShinkaEvolve，5 代，best，12 实例集） | 99.31 |
| agent（ShinkaEvolve，5 代，best，**24 实例集**） | **98.65** |
| agent（AB-MCTS，5 候选，best，12 实例集） | 98.70 |
| agent（AB-MCTS，5 候选，best，**24 实例集**） | **99.26** |

baseline 在 24 个实例上的分数分布（`python verification/evaluator.py baseline/solver.py`）：mean **54.69**、std 7.32、min 44.03（`VHO-51-7`）、max 71.55（`VRP-21-3`）。求解器是确定性的（固定种子 RNG），重复运行逐字节一致；上述离散度是跨实例的，而非跨 seed 的。

**多 seed 统计**（评审要求的 "multi-run statistics"）：`verification/multiseed_stat.py` 从多个 seed 派生全新评测实例集并现场计算各集参考距离（`python verification/multiseed_stat.py --seeds 111 222 333`）：

| Seed | combined_score |
|------|----------------|
| 111  | 57.24 |
| 222  | 59.86 |
| 333  | 56.09 |
| **mean ± std** | **57.73 ± 1.58**（min 56.09，max 59.86） |

**Agent 多运行统计**（每框架 3 次运行，24 实例集，`deepseek-v4-flash`；完整运行 ID 见"实验记录"）：

| 框架 | 各次 combined_score | mean | std | min | max |
|------|---------------------|------|-----|-----|-----|
| openevolve（5 轮） | 98.00, 97.96, 97.47 | **97.81** | 0.24 | 97.47 | 98.00 |
| ShinkaEvolve（5 代） | 98.13, 54.69\*, 98.65 | **83.82** | 20.60 | 54.69 | 98.65 |
| AB-MCTS（5 候选） | 98.49, 96.78, 99.26 | **98.18** | 1.04 | 96.78 | 99.26 |

\* 有一次 ShinkaEvolve 运行在每一代都生成了无效程序（各代计 0 分），其 best 停在 baseline 54.69——这是真实的失败模式，不是环境问题。

agent 分数为随机进化运行的 "best found"；有多次运行的一并列出（如 openevolve 96.38 与 95.65，见"实验记录"）。

## 评测完整性

- **Held-out 实例**：12 个 `VHO-*` 实例位于 `data/instances_heldout/`，把评测集扩充到 24 个并与公开实例一起评分。它们的 `.vrp` 文件**不复制进评测沙箱**：评测器从宿主（`FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR`）读取路径，只在评分该实例时把路径交给候选。这些文件在仓库里是公开的，运行中的候选收到路径后确实能读到文件（见下方威胁模型）；`Task.md` 和 `constraints.txt` 会告知 agent 存在这类 held-out 实例且会被评分，但代码生成时拿不到它们的实例数据，因此 LLM 无法按实例名硬编码路线；`validator.py` 还会静态拒绝按实例名硬编码，`CVRP_EVAL_GENERATE_SEED` 则让评分时的实例集不可预测。
- **评测时生成实例**：设置 `CVRP_EVAL_GENERATE_SEED`（可选 `CVRP_EVAL_GENERATE_COUNT`，默认 6），评测器会在评分时用该种子**现场生成全新实例**参与评分，每个生成实例的参考距离由参考求解器当场计算——这样即使候选见过所有公开实例文件，也无法背答案。同一种子 ⇒ 同一批实例 ⇒ 完全可复现。直跑评测器与 unified 运行时（process 模式）均支持；docker 隔离模式（Linux/WSL）下评分可用（靠 `eval_command.txt` 的 `{benchmark_source}` 注入），但运行时生成不可用——unified 运行时不会把种子环境变量传入容器（框架级限制）。
- **沙箱隔离**：`copy_files.txt` 只把 `baseline/`、`data/instances/`、`frontier_eval/` 复制进评测沙箱（held-out 实例与 `reference.json` 从宿主读取、从不复制）。`frontier_eval/evaluator.py` 是自包含的（解析、校验、评分与完整性检查全部内嵌），因此**任何 `verification/` 文件（包括参考求解器）都不复制**。`reference.json` 从不复制；评测器通过 `FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR` 从宿主读取参考距离，候选子进程运行时**所有 `FRONTIER_*` 变量都被剥离**（外加参考/生成设置），无法得知宿主仓库路径——这封死了 `FRONTIER_ENGINEERING_ROOT` 侧信道（否则候选可借此找到并导入宿主上的 `verification/ref_solver.py`）。
- **Preflight 检查**（`verification/validator.py`）：评测器会静态拒绝修改 EVOLVE-BLOCK 区外代码、引用 `verification` / `ref_solver` / `reference.json`、含绝对路径、或按实例名硬编码路线的候选；另有**确定性探针**——在最小 / 中等 / 最大 3 个代表实例上把候选各跑两次，输出不一致（非确定性）即判无效。
- **威胁模型**：所有实例文件（公开与 held-out）在仓库和评测沙箱里都可见——能读到仓库的人总能手写一个求解器，任何 benchmark 都无法阻止这一点。防护是威慑级的：constraints 禁止读取参考与按实例名硬编码，`validator.py` 静态拒绝此类尝试，`CVRP_EVAL_GENERATE_SEED` 让评分时的实例集不可预测。unified 运行时（process 与 docker 隔离）会把宿主仓库暴露给候选进程（这是所有任务共享的框架级行为）。评分只衡量解的质量，从不看代码来源。

## 实验记录

所有 agent 运行均使用 `deepseek-v4-flash` 模型。分数为 "best found"；LLM 进化具有随机性，有多次运行的地方一并列出。

| 运行 | 框架 | 分数 | 评测集 |
|------|------|------|--------|
| baseline（随机顺序最近插入） | — | 54.69 | 24 实例（12 公开 + 12 held-out） |
| reference（GRASP + LNS，评分基准） | — | 100 | 24 实例 |
| `runs/.../openevolve/deepseek-v4-flash/20260807_170244` | openevolve，5 轮 | 96.38 | 12 公开 |
| `runs/.../openevolve/deepseek-v4-flash/20260807_195321` | openevolve，5 轮 | 95.65 | 12 公开 |
| `runs/.../openevolve/deepseek-v4-flash/20260811_215703` | openevolve，5 轮 | 98.00 | 24 实例（12 公开 + 12 held-out） |
| `runs/.../openevolve/deepseek-v4-flash/20260812_172944` | openevolve，5 轮 | 97.96 | 24 实例（12 公开 + 12 held-out） |
| `runs/.../openevolve/deepseek-v4-flash/20260812_174122` | openevolve，5 轮 | 97.47 | 24 实例（12 公开 + 12 held-out） |
| `runs/.../shinkaevolve/deepseek-v4-flash/20260807_195503` | ShinkaEvolve，5 代 | 99.31 | 12 公开 |
| `runs/.../shinkaevolve/deepseek-v4-flash/20260811_192446` | ShinkaEvolve，5 代 | 98.13 | 24 实例（12 公开 + 12 held-out） |
| `runs/.../shinkaevolve/deepseek-v4-flash/20260812_175208` | ShinkaEvolve，5 代 | 54.69\* | 24 实例（12 公开 + 12 held-out） |
| `runs/.../shinkaevolve/deepseek-v4-flash/20260812_175816` | ShinkaEvolve，5 代 | 98.65 | 24 实例（12 公开 + 12 held-out） |
| `runs/.../abmcts/deepseek-v4-flash/20260807_190515` | AB-MCTS，5 候选 | 98.70 | 12 公开 |
| `runs/.../abmcts/deepseek-v4-flash/20260812_102741` | AB-MCTS，5 候选 | 98.49 | 24 实例（12 公开 + 12 held-out） |
| `runs/.../abmcts/deepseek-v4-flash/20260812_181308` | AB-MCTS，5 候选 | 96.78 | 24 实例（12 公开 + 12 held-out） |
| `runs/.../abmcts/deepseek-v4-flash/20260812_182222` | AB-MCTS，5 候选 | 99.26 | 24 实例（12 公开 + 12 held-out） |

baseline 复现：

```bash
# 在 CVRP 目录下
python verification/evaluator.py baseline/solver.py     # -> 54.69, valid 1.0（24 实例）
python verification/test_evaluator.py                   # -> 23 个单元测试全部通过
python verification/test_validator.py                   # -> 16 个单元测试全部通过
python verification/test_ref_solver.py                  # -> 5 个单元测试全部通过
python verification/test_frontier_eval_evaluator.py     # -> 6 个单元测试全部通过（沙箱版）
python verification/multiseed_stat.py --seeds 111 222 333  # -> 57.73 ± 1.58
```

框架适配验证（仓库根目录）：

```bash
# process 模式
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0

# docker 隔离（先构建镜像：docker build -t cvrp-benchmark -f verification/docker/Dockerfile .）
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0 task.runtime.isolation_mode=docker task.runtime.docker_image=cvrp-benchmark
```

## Unified-task 集成

- **Benchmark id**：`VehicleRouting/CVRP`
- 评测器仅使用 Python 标准库，因此**无需任何 runtime 覆盖项**（不需要 `python_path`、conda 环境或 Docker 镜像指定）；`eval_command.txt` 直接使用 `{python}`。
- 仅 Windows：本地验证需将 `task.runtime.shell` 指向 Git Bash（如 `task.runtime.shell=C:/Program Files/Git/bin/bash.exe`），因为默认 `bash` 会解析到没有 `python` 的 WSL 垫片（returncode 127）。Linux 无需覆盖。
- 框架适配验证命令（仓库根目录）：
  `python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0`
