# 连铸切割优化（离线/静态版，CuttingOptimization）

## 1. 背景

连铸是把钢水变成钢坯的生产过程：钢水从中间包连续浇入结晶器，按固定拉坯速度往下拉，
经二冷段凝固成钢坯，再按尺寸要求切割。切割机有一个固定的工作起点，切割必须从该起点开始。

当结晶器出现异常时，钢坯内会形成一小段"报废段"（本任务中统一为 **0.8 m**），必须被切出
并报废。切割方案要同时满足两条要求（字典序）：

1. **优先最小化切割损失**：切割损失 = 报废钢坯的总长度。
2. **其次满足用户需求**：在损失相同的方案中，切出的成品尽量贴近用户目标值。

本任务把赛题抽象成一个**确定性的一维切割优化**问题：钢坯是一根一维线段，上面带若干
零废段；求解器要给出一个把整根钢坯（含必须切出的零废段）完全切成段的切割方案，使报废
长度最小、成品贴合目标值。

## 2. 输入（实例）

实例是一个 JSON 文件，由 `verification/generator.py` 按种子生成（评测时实时生成，不可预记忆）：

```json
{
  "seed": 3,
  "process": {"speed": 1.0, "cut_time": 3, "return_time": 1, "buffer_len": 60, "scrap_len": 0.8},
  "billet": {"total_length": 106.2},
  "customer": {"target": 8.5, "target_min": 8.0, "target_max": 9.0},
  "defects": [[21.3, 22.1], [42.5, 43.3], [60.1, 60.9]],
  "limits": {"min_basic": 4.8, "max_basic": 12.6, "min_process": 8.0, "max_process": 11.6}
}
```

含义：
- `billet.total_length`：钢坯总长 S，线段 `[0, S]`。
- `customer.target` / `target_min` / `target_max`：用户目标值及可接受的切段长度窗口。
- `defects`：零废段区间 `[a, b)`（每段长 0.8 m）。它们把 `[0, S]` 分成若干"干净坯段"。
- `limits`：三段长度窗口
  - `[min_basic, max_basic] = [4.8, 12.6]`：能运走的最小/最大长度（硬约束）。
  - `[min_process, max_process] = [8.0, 11.6]`：下道工序可直接接受的长度。
  - 用户窗口 `[target_min, target_max]`：零报废的理想段长范围。

时间参数（拉坯速度 1.0 m/min、切一块 3 min、回程 1 min、结晶器到切割机 60 m）在
`process` 里给出，仅作为物理背景。由于两次切割最小间隔对应材料长度
`1.0×(3+1)=4 m < 4.8 m`，**切割机总能跟上，时间不构成约束**，故不参与评分。

## 3. 输出（求解格式）

求解器以 `python baseline/solver.py <instance.json>` 运行，向 stdout 打印一个 JSON：

```json
{"cuts": [9.5, 9.4, 8.8, 0.8, 10.0, ...]}
```

`cuts` 是切段长度列表，依次排开**恰好铺满整个 `[0, S]`**（含每个零废段这个 0.8 m 的小块）。
即 `sum(cuts) == total_length`（容差 1e-3）。

## 4. 合法性校验（硬约束）

1. `sum(cuts) ≈ S`（容差 1e-3）。
2. 每块长度必须在 `[4.8, 12.6]`，**除非**它恰好是某个零废段（0.8 m 小块，允许出现）。
3. 切口必须对齐每个零废段的两个端点：零废段必须被单独切出（其两端必须是切点）；
   任何跨过零废段的成品块都会污染，判非法。

违反任一硬约束 ⇒ 该实例记 0 分。

## 5. 评分函数

每块长度 `c` 的报废与贴合度：

- `c < 8.0`（且非零废段小块）：送不到下道工序 → 整块报废，`scrap += c`。
- `c >= 8.0`：可送下道。超出 `target_max` 的部分报废，`scrap += c - min(c, target_max)`。
- `target_min <= c <= target_max`：零报废、零惩罚（完美块）。
- `c < target_min`（但 `c >= 8.0`）：能送但偏短 → 零报废、贴合度惩罚。

贴合度惩罚：`penalty = |min(c, target_max) - target|`（实际交付长度与目标值的距离）。

指标：**材料利用率** `util = 100 * (S - (scrap + 1e-4*penalty)) / S`，多实例取平均（0~100，越高越好）。
其中 `score = scrap + 1e-4*penalty`，`1e-4` 极小，保证**先最小化报废、再最小化贴合度**（字典序），
`util` 略随贴合度变化以破平。

> 说明：`penalty` 项只对非零废段的成品块计算；零废段小块只计入报废，不参与贴合度。

## 6. 参考分数（固定 8 实例，`verification/evaluate.py` 实测）

| 求解器 | 平均利用率 | 平均报废(m) |
|---|---|---|
| baseline（均匀等分） | 72.5 | 25.2 |
| ref_solver（一维划分 DP，最优） | 88.7 | 10.6 |

各实例参考利用率：95.8 / 88.8 / 91.8 / 75.2 / 92.4 / 87.0 / 89.4 / 89.3。

> agent/框架分数（统一 low 推理）：openevolve **88.7**（= 参考解）、ShinkaEvolve **88.4**、
> AB-MCTS **72.5**（= baseline，本轮未提升）。诚实说明：**该任务的最优是可达的**——强 agent
> 能推导出精确划分 DP 并打到 ~88.7 = 天花板；难度在"推导 DP"而非长程搜索。更难的**在线版**
> （`CuttingOptimizationOnline`）才是信息不对称让 agent 打不满全知最优（见其 README）。

## 7. 接口契约与约束

- 只允许修改 `baseline/solver.py` 的 `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END` 区域；
  标记外的代码必须与初始 baseline 逐字节一致。
- 输出必须始终是合法切割方案；越界、未对齐零废段、崩溃或超时 ⇒ 该实例 0 分。
- 允许 `import verification/simulator.py`（只读，用于搜索时评估候选方案）；
  **禁止** import / 读取 `verification/generator.py`、`verification/ref_solver.py`、
  `verification/evaluate.py`。
- 单实例时间预算默认 60 s，`--time-budget` 可调（挑战档 10 s）。
