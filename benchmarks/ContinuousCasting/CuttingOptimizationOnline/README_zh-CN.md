# CuttingOptimizationOnline：连铸切割的在线优化（Frontier-Eng 基准）

一个**原创**的 Frontier-Engineering 基准，是离线版
[CuttingOptimization](../CuttingOptimization/README_zh-CN.md) 的**在线（闭环）**扩展，题材取自 2021 全国大学生数学建模竞赛 D 题。

一根连续浇铸的钢坯被拉过切割机。**结晶器异常会产生 0.8m 报废段，但 agent 只在报废段距切割线 `reveal_lead` 米以内时才被告知**（本基准最终配置 `reveal_lead=10` → 隐藏异常；`reveal_lead=60` 为"忠实版"，此时 agent 能看到所有相关异常）。agent **每个切割决策点被调用一次、只拿到当下可见状态**，永远看不到未来，并要选下一刀长度。最后按**完整隐藏报废表**评分：任何与报废段重叠的切块都被污染、整块报废。

完整规则与评测语义见 [Task.md](./Task.md)。

## 目录结构

```
benchmarks/ContinuousCasting/CuttingOptimizationOnline/
├── baseline/solver.py          # agent 求解器：decide(state)->切长（EVOLVE-BLOCK 可改）
├── verification/
│   ├── generator.py            # 种子实例生成器（隐藏异常表 + reveal_lead）
│   ├── simulator.py            # 闭环模拟器 + 污染/报废评分
│   ├── evaluate.py             # 每决策点闭环评测入口
│   ├── validator.py            # 完整性校验（静态 + FRONTIER_* 剥离 + 确定性）
│   ├── ref_solver.py           # 全知参考解 DP（看全异常）—— 理论天花板
│   ├── multiseed_stat.py       # 多轮均值±std 工具
│   ├── test_simulator.py       # 单测：评分/合法性
│   ├── test_generator.py       # 单测：确定性/隐藏表/reveal_lead
│   ├── test_ref_solver.py      # 单测：参考解合法性 + 优于基线
│   ├── test_validator.py       # 单测：静态检查/环境剥离
│   ├── test_evaluator.py       # 单测：闭环评测/作弊拒绝/生成
│   ├── test_frontier_eval_evaluator.py  # 单测：沙箱入口
│   ├── data/instances/         # 8 个固定实例（种子固定）
│   ├── docker/Dockerfile       # 最简 python:3.11-slim 镜像
│   └── requirements.txt
├── frontier_eval/              # UnifiedTask 元数据（OpenAI-compatible LLM）
├── Task.md                     # 正式模型、接口、评分、参考分
└── README_zh-CN.md
```

## 运行

```powershell
# 在固定 8 实例上给 baseline 打分（每决策点闭环）
python verification/evaluate.py baseline/solver.py --reveal-lead 10

# 加运行时生成实例（防硬编码）
$env:ONLINE_CUT_EVAL_GENERATE_SEED = "<SEED>"
python verification/evaluate.py baseline/solver.py

# 多轮统计（mean±std）
python verification/multiseed_stat.py --runs-dir runs/unified__ContinuousCasting__CuttingOptimizationOnline/openevolve
```

### 用 OpenAI-compatible proxy（agent 搜索必需）

`deepseek-v4-flash` 是思考型模型，可能吃光 token 预算而返回空 content。需要：

1. **让 LLM 走代理**：抬高 `max_tokens` 并注入低 `reasoning_effort`，如
   `PROXY_PORT=8765 REASONING_MODE=low MAX_TOKENS=32768 python deepseek_proxy.py`，再 `OPENAI_API_BASE=http://127.0.0.1:8765/v1`。
2. **shinkaevolve 会用 `override=True` 加载 `.env`**，把 `OPENAI_API_BASE` 覆盖掉、从而绕过代理——**必须用 hydra 覆盖 `llm.api_base=http://127.0.0.1:8765/v1`**（配置值，非环境变量）。openevolve / abmcts 直接读 `OPENAI_API_BASE`，无需此步。

## 测试

```powershell
python -m unittest discover -s verification -p "test_*.py"
```

23 个单测（simulator / generator / ref_solver / validator / evaluator / 沙箱 evaluator）：
评分与合法性（污染、短尾当报废）、确定性生成、参考解合法且优于基线、validator 完整性
（EVOLVE-BLOCK / 禁引用 / 绝对路径 / `FRONTIER_*` 剥离 / 确定性）、闭环评测（作弊候选被拒、
运行时生成）、以及沙箱入口一致性。

## 完整性 / 威胁模型

- `verification/ref_solver.py` 与 `generator.py` **不**进沙箱，且被 validator 禁用
  （`ref_solver`、`generator`、`anomaly_seed` token）。
- 候选子进程剥离**所有 `FRONTIER_*`** 与 `ONLINE_CUT_EVAL_*` 变量（`candidate_env`），
  封宿主侧信道。
- **运行时生成**（`ONLINE_CUT_EVAL_GENERATE_SEED`）评测时现场生成实例，候选无法预记忆。
  （固定种子可预测；要真正防指纹，runner 每轮用新种子。）
- 确定性探针：对探针实例跑两遍闭环，切段序列必须一致。
- 诚实说明：process 模式下候选有主机文件系统访问（框架级限制）；本基准依赖上述分层防御。

## 评分

- **指标**：材料利用率 `util = 100*(S - scrap)/S`，多实例取平均（0~100，越高越好）。
  `scrap` = 污染块（与任一报废段重叠即整块报废）+ 干净块 <8m 整块报废 + 干净块超 `target_max`
  的余量报废，外加一个极小贴合度惩罚 `1e-4 * Σ|交付 - target|` 破平。
- **污染不可避免**：最小切段 4.8m > 0.8m 报废段，报废段永远无法单独切出，必污染 ≥4.8m 成品。
  这正是"在线难度"与信息不对称的来源。
- **参考分（固定 8 实例）**：baseline（恒定目标贪心）= **52.4**；全知 DP（`ref_solver.py`，
  看全异常）= **76.4**。全知是**理论天花板**——看不到未来的在线 agent **无法达到它**。

### Agent 分（最终配置 `reveal_lead = 10`；统一 low 推理，各 15 代，每框架 3 次）

| 框架 | 次1 | 次2 | 次3 | mean ± std |
|---|---|---|---|---|
| openevolve | 69.48 | 70.10 | 70.10 | **69.89 ± 0.36** |
| shinkaevolve | 70.06 | 71.18 | 70.10 | **70.45 ± 0.64** |
| abmcts | 72.31 | 70.10 | 70.45 | **70.95 ± 1.19** |

9 次合计：mean **70.43 ± 0.83**；全知 reference（看全异常）= **76.4**（差 ≈6.0），baseline（恒定目标贪心）= **52.4**。

观察：**每一次都低于全知天花板（76.4）、高于 baseline（52.4）**——即隐藏异常的信息不对称
**确实让在线 agent 无法达到全知最优**，三个框架一致。这是与离线版的关键差别（离线版 openevolve
能精确达到离线最优）。各框架 spread 小（std≈0.4–1.2），agent 分数聚在"安全短切"平台（~70）附近，
正是"看不到未来"限制住 agent 的地方。

> 诚实说明：agent 改进呈**阶梯式跳变**（卡 baseline 多代、某次突变到 ~70），不是渐进爬升——符合
> "强约束下把策略一次想对"胜过增量搜索。AB-MCTS 那次高分（72.31）与其 std（1.19）反映的是
> 运行间随机性，不是系统性优势。

> 方法学说明：以上"在线 agent 无法达到全知最优"是**经验观察**（3 框架 × 3 次均在 ref 之下），
> 尚无"在线策略最优下界"的严格证明；若需坐实，可另加一个"只限可见信息、按揭示窗口保守决策"的
> 在线 oracle 层作为参照。

## Docker

提供最简 `python:3.11-slim` 镜像（`verification/docker/Dockerfile`）。构建镜像后用 unified 的
`isolation_mode=docker`（WSL/Linux；Windows 宿主受框架路径 bug 限制）。**已在 WSL 下实测通过**：
基线 `combined_score=52.40, valid=1.0, num_instances=8`，与 process 模式一致。这也再次验证了在线版
防作弊在容器里同样成立——固定实例（含隐藏报废表）**不进沙箱**，评测器从宿主源 benchmark 目录
（`{benchmark_source}` → 容器内挂载的 repo 路径）加载，候选在容器内读不到隐藏报废表。
