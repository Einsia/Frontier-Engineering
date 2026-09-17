# Task：容量约束车辆路径问题（CVRP）

## 受众与假设

本任务假设你有一般 CS 背景，但对组合优化 / 车辆路径问题没有或只有很少了解。

## 问题背景

物流配送中，一辆辆货车从仓库出发为客户送货。**容量约束车辆路径问题（CVRP）** 是它的标准数学模型：

- **仓库（depot）**：编号 0，所有车辆从这里出发并返回。
- **客户**：编号 1..n，每个客户有需求量 `demand[c]`。
- **车辆**：同型，容量上限 `capacity`。
- **路线**：每条路线为 `仓库 → 若干客户 → 仓库`，且路线内总需求 ≤ 容量。

目标：用若干条路线服务**所有**客户（每个客户恰好被服务一次），使**总行驶距离最小**。

CVRP 是 NP-hard 问题，几十个客户的实例无法精确求解，必须使用启发式方法（最近邻、savings、2-opt、大邻域搜索、元启发式等）。

## 实例（data/instances/、data/instances_heldout/）

本任务提供 24 个确定性生成的聚簇分布实例（模拟城市客户分布，坐标 1..100，距离四舍五入取整）：

- **12 个公开实例**（data/instances/，`VRP-*`）：

| 实例 | 客户数 | 容量 | 实例 | 客户数 | 容量 |
|------|--------|------|------|--------|------|
| VRP-19-2 | 19 | 270 | VRP-45-7 | 45 | 150 |
| VRP-21-3 | 21 | 165 | VRP-48-7 | 48 | 170 |
| VRP-22-4 | 22 | 130 | VRP-54-8 | 54 | 175 |
| VRP-32-5 | 32 | 160 | VRP-55-8 | 55 | 185 |
| VRP-37-6 | 37 | 145 | VRP-60-9 | 60 | 160 |
| VRP-45-6 | 45 | 190 | VRP-60-10 | 60 | 165 |

- **12 个 held-out 实例**（data/instances_heldout/，`VHO-*`）：与公开实例一起在评测时打分，把评测集扩充到 24 个。它们的文件**留在宿主、不复制进评测沙箱**，开发阶段你读不到它们——评分时才把每个路径交给你的求解器。按实例名硬编码会被静态检查拒绝，`CVRP_EVAL_GENERATE_SEED` 还可在评测时现场加入新实例，让评分实例集不可预测。在 held-out 集上打分衡量 agent 是否学到了**可泛化**的求解方法。

文件名即实例名（如 `VRP-19-2.vrp`），采用 TSPLIB 风格格式（`NODE_COORD_SECTION` / `DEMAND_SECTION` / `DEPOT_SECTION`，depot 为节点 1）。实例由 `verification/generate_instances.py` 确定性生成（seed 42，`seed_key` 固定为发布时的原始标识符，保证数据集跨版本逐字节稳定）。

## 输入 / 输出契约

### 候选程序 `baseline/solver.py`

```python
# EVOLVE-BLOCK-START
def solve(instance):
    """输入 instance dict，输出路线列表 list[list[int]]。
    每个子列表是一条路线的客户访问序列（客户编号 1..n，不含仓库 0）。"""
    ...
# EVOLVE-BLOCK-END
```

- `instance` 字段：
  - `n`：客户数（客户编号 1..n，仓库为 0）
  - `capacity`：车辆容量
  - `demand`：`demand[0..n]`，`demand[0] == 0`
  - `distance`：`(n+1)×(n+1)` 的欧氏四舍五入取整距离矩阵，`distance[0][c]` 为仓库到客户 c 的距离
- 输出：`list[list[int]]`。每条路线为**客户编号序列**（不含仓库 0），例如 `[[3,1,5],[2,4]]` 表示两辆车。
- 独立运行：`python baseline/solver.py <instance.vrp> <output.json>`（固定 I/O 部分不可修改）。

### 验证规则

对候选输出逐条检查：
1. 格式合法：`routes` 是列表的列表，元素为 1..n 的整数；
2. **全覆盖**：所有路线的客户并集恰好为 {1..n}（无重复、无遗漏）；
3. **容量**：每条路线 `sum(demand[c]) ≤ capacity`。

任一不满足 → 该实例判 invalid，得 0 分，且整个候选 `valid=0`。

### 候选完整性检查（preflight）

运行前，评测器会**静态拒绝**有以下行为的候选：
- 删除或重排 `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END` 标记，或修改 evolve 区外、与初始 baseline 不一致的代码；
- 引用 verification 模块、参考求解器或 `reference.json`（如 `import verification.ref_solver`）；
- 含绝对文件系统路径；
- 按实例名硬编码路线（如 `"VRP-19-2": [...]`）。

违规候选得 0 分并判无效。候选子进程运行在剥离宿主路径的环境中，无法定位宿主上的 `reference.json`；评测沙箱只包含候选需要的文件（实例 + 评测胶水），**从不包含参考求解器或 `reference.json`**。

## 评分

```
score_instance = min(100, 100 × reference_distance / candidate_distance)
combined_score = mean(score_instance)     # 跨 24 个实例平均（12 公开 + 12 held-out）
valid          = 全部实例合法？1 : 0
```

- `reference_distance` 来自 `data/reference.json`，由 `verification/ref_solver.py` 预计算：**确定性**的 GRASP 多起点 + 2-opt + relocate/swap + 2-opt* + LNS（贪心修复 + tabu 多样化），对固定种子列表 `(123, 2024, 7)` 逐实例取最优，任何机器上重新生成均字节一致。参考解为近最优（与本任务存档的 agent 最优解、OR-Tools GLS 交叉验证一致）。
- **100 分 = 达到参考求解器的解质量**；候选解比参考解更短时可超过 100 分（被截断在 100）。达到 100 意味着已经逼近该实例的实际最优。
- 可选评分旋钮 `CVRP_EVAL_SCORE_SCALE`（默认 1.0）：`score = min(100, scale × 100 × ref / cand)`。scale < 1 会收紧 100 分线（如 scale=2/3 要求候选距离 ≤ 参考的 2/3 才能得 100）。
- 非法 / 崩溃 / 超时的候选：对应实例 0 分，且 `valid=0`（整体判负）。

## 如何运行

```bash
# 在 CVRP 目录下评测一个候选求解器
python verification/evaluator.py baseline/solver.py

# 只评测部分实例
python verification/evaluator.py baseline/solver.py --instances VRP-19-2 VRP-32-5

# 运行单元测试（评测器 / 验证器 / 候选检查）
python verification/test_evaluator.py

# 框架适配验证（仓库根目录，process 模式）
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0

# 框架适配验证（仓库根目录，docker 隔离；需先构建镜像：
# docker build -t cvrp-benchmark -f verification/docker/Dockerfile .）
python -m frontier_eval task=unified task.benchmark=VehicleRouting/CVRP algorithm.iterations=0 task.runtime.isolation_mode=docker task.runtime.docker_image=cvrp-benchmark
```

环境变量：`CVRP_EVAL_TIMEOUT_S`（每实例子进程超时，默认 60）、`CVRP_EVAL_INSTANCES`（实例子集）、`CVRP_EVAL_MAX_INSTANCES`（实例数上限）、`CVRP_EVAL_SCORE_SCALE`（评分旋钮，默认 1.0）。

## 参考分数（本机实测，对当前 reference.json）

当前评测集为 24 个实例（12 公开 + 12 held-out）。下面的 agent 分数是在**较早的 12 公开实例集**上测得的（held-out 实例为后加），保留用于跨框架对比；在完整 24 实例集上的新运行（ShinkaEvolve 98.65、openevolve 98.00、AB-MCTS 99.26）证明学到的求解器能泛化到未见过的实例。运行记录与多运行统计见 README "Experiments"。

| 求解器 | combined_score |
|--------|----------------|
| baseline（随机顺序最近插入），24 实例 | **54.69** |
| reference（确定性 GRASP + LNS，评分基准） | 100（近最优） |
| agent（openevolve 5 轮，best，12 实例集） | 96.38 |
| agent（openevolve 5 轮，best，24 实例集） | 98.00 |
| agent（ShinkaEvolve 5 代，best，12 实例集） | 99.31 |
| agent（ShinkaEvolve 5 代，best，24 实例集） | 98.65 |
| agent（AB-MCTS 5 候选，best，12 实例集） | 98.70 |
| agent（AB-MCTS 5 候选，best，24 实例集） | 99.26 |

## 优化提示（由弱到强）

1. **随机顺序最近插入**（baseline）：按随机顺序逐个把客户插入到所有路线中代价最小的可行位置 —— 弱但标准的随机化构造。
2. **Clarke-Wright savings**：按 `d(0,i)+d(0,j)-d(i,j)` 降序合并路线 —— 明显改进。
3. **路线内 2-opt**：翻转路线片段消除交叉 —— 进一步改进。
4. **跨路线局部搜索**：relocate / swap / 2-opt*。
5. **大邻域搜索（LNS）/ 模拟退火 / 遗传**：接近参考甚至超越参考。

每一步都是可验证的分数提升。**先保证合法（全覆盖 + 容量），再优化距离。**
