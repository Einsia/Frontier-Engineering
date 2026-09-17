# CuttingOptimization：连铸切割优化（离线/静态版，Frontier-Eng 基准）

一个**原创**的 Frontier-Engineering 基准，灵感来自 2021 全国大学生数学建模竞赛 D 题
《连铸切割的在线优化》，并被形式化成**确定性、自包含**的切割优化任务。

一根连续浇铸的钢坯以固定速度被拉出；结晶器异常会在坯内产生 **0.8 m 的零废段**，必须被
切出并报废。求解器收到钢坯长度、零废段位置、以及一个"目标值 + 可接受窗口"的用户需求后，
要给出一个**切割方案**（一组恰好铺满整根钢坯的切段长度），使**报废总长度最小**，并让
**每块成品尽量贴近目标值**。

完整规则与评测语义见 [Task.md](./Task.md)。

## 目录结构

```
benchmarks/ContinuousCasting/CuttingOptimization/
├── baseline/solver.py          # 候选求解器（仅 EVOLVE-BLOCK 区域可改）
├── verification/
│   ├── generator.py            # 固定种子实例生成器（零废段 + 目标窗口）
│   ├── simulator.py            # 计分模拟器（校验 + 报废 / 贴合度指标）
│   ├── evaluate.py             # 评测入口（subprocess + 时间预算 + 打分）
│   ├── validator.py            # 完整性校验（静态 + 环境剥离 + 确定性）
│   ├── ref_solver.py           # 参考解（一维划分 DP；文档化的"最优"分）
│   ├── test_simulator.py       # 单测：计分器正确性
│   ├── test_generator.py       # 单测：确定性 / 零废段可行性 / headroom
│   ├── test_ref_solver.py      # 单测：参考解合法性 + 最优性
│   ├── test_validator.py       # 单测：完整性校验 / 环境剥离 / 确定性
│   ├── test_evaluator.py       # 单测：端到端评测行为
│   ├── data/instances/         # 8 个固定实例（种子固定、可复现）
│   ├── docker/Dockerfile       # 极简纯标准库 python 镜像
│   └── requirements.txt
├── frontier_eval/              # UnifiedTask 元数据
├── Task.md                     # 任务规则、接口、评分、参考分
└── README_zh-CN.md
```

## 运行

```powershell
# 在固定 8 实例上给求解器打分（默认每实例 60s）
python verification/evaluate.py baseline/solver.py

# 加运行时生成实例（防硬编码）
python verification/evaluate.py baseline/solver.py --generate-seed <SEED>

# 更紧的时间预算（挑战档 10s）
python verification/evaluate.py baseline/solver.py --time-budget 10
```

## Docker

提供最简 `python:3.11-slim` 镜像（`verification/docker/Dockerfile`）。构建后用 unified 的
`isolation_mode=docker`（WSL/Linux；Windows 宿主受框架路径 bug 限制）。**已在 WSL 下实测通过**：
基线 `combined_score=72.49, valid=1.0, num_instances=8`，与 process 模式一致。

## 测试

```powershell
python -m unittest discover -s verification -p "test_*.py"
```

共 35 个单测（simulator / generator / ref_solver / validator / evaluator / 沙箱 evaluator 六个模块）：
单块报废与贴合度规则、合法校验（求和、长度窗口、零废段对齐）、生成与参考解的确定性、
参考解优于 baseline 的最优性、validator 完整性（EVOLVE-BLOCK / 禁引用 / 绝对路径 /
按实例名硬编码 / 环境剥离 / 确定性探针）、以及 evaluator 行为（打分、运行时生成、
作弊候选被拒）、`frontier_eval/evaluator.py` 沙箱入口一致性。`verification/multiseed_stat.py`
用于多轮均值±std。

## 完整性 / 威胁模型

- **运行时生成实例**：设置 `CUTTING_EVAL_GENERATE_SEED` 后，评测现场生成新实例（临时目录，
  不进仓库/沙箱），候选无法预先记忆。
- **候选环境剥离**：候选子进程剥离 `FRONTIER_*` / `CUTTING_EVAL_*` 变量（见 validator.py）。
- **静态检查**：EVOLVE-BLOCK 标记 + 固定区字节比对、禁引用评测/生成/参考解模块、绝对路径、
  按实例名硬编码、确定性探针（两次运行输出一致）。任何违规记 0 分。
- **沙箱范围**：8 个固定实例、evaluator/validator 源码对候选可见（打分需要，且
  `verification/simulator.py` 有意作为白盒计分器）；防硬编码依赖 `CUTTING_EVAL_GENERATE_SEED`。
  `verification/ref_solver.py` 与 `verification/generator.py` **不**复制进沙箱，并被 validator 额外禁用。
- 说明：在进程模式下候选有主机文件系统访问（框架级限制），本基准依赖上述分层防御。

## 评分

- 实例 = 8 固定（easy/medium/hard，S=24..150 m，0..6 个零废段，目标窗口 ±0.5 m）+ 设置
  `CUTTING_EVAL_GENERATE_SEED` 时的运行时生成实例。
- **指标**：材料利用率 `util = 100 * (S - (scrap + 1e-4*penalty)) / S`，多实例取平均（0~100，越高越好）。
  `scrap` = 总报废长度（零废段小块 + <8.0 m 整损 + 超出窗口的余量）；`penalty = Σ|交付 - 目标|`；
  `1e-4` 权重极小，保证报废严格占主导（惩罚仅在报废相同时破平），符合赛题的字典序目标。
- 非法输出 / 越界切段 / 未对齐零废段 / 崩溃 / 超时 ⇒ 该实例 0 分。
- **headroom 保证**：生成器只接受"参考解严格优于朴素等分 ≥ 0.1 m 报废"的实例，
  保证每个实例都有真实优化信号。
- 参考分（固定 8 实例实测）：
  - baseline（均匀等分）：**72.5** 利用率（平均报废 25.2 m）
  - ref_solver（一维划分 DP）：**88.7** 利用率（平均报废 10.6 m）
  - agent（openevolve，10 代，best 保存程序）：**88.7** 利用率（run `20260903_130517`）——**恰好等于参考解 DP**。
  - agent（ShinkaEvolve，15 代，经推理代理）：**88.4** 利用率（run `20260904_182017`，接近最优）。
  - agent（AB-MCTS，15 迭代）：**72.5** 利用率（= baseline；本轮未提升——AB-MCTS 在此较弱，低推理下多数改进突变回归/无效）。
  - 诚实设计说明：离线最优是**可达的**（强 agent 能推导出精确的一维划分 DP 并打到 88.7 = 天花板）。
    所以离线任务的难度在"推导 DP"，不在长程搜索。更难的**在线版**
    （`CuttingOptimizationOnline`）才是信息不对称让 agent 无法达到全知天花板——见该 README 的 3×2 矩阵。
  - `verification/multiseed_stat.py` 用于跨框架运行目录做多轮均值±std。
