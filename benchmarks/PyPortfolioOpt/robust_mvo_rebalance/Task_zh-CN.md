# 任务 01 说明：鲁棒 MVO 再平衡

## 背景

你在实现一个股票组合再平衡器。
策略给出预期收益 `mu` 和协方差 `Sigma`，但风控和交易要求还要满足：
- 个股仓位上下界，
- 行业暴露上下界，
- 风格/因子暴露上下界，
- 相对当前持仓的换手上限，
- L1 交易惩罚。

这是一个带约束的凸优化问题。

## 输入

求解器接收一个 Python `dict`（命名为 `instance`）：

- `mu`: `np.ndarray`，形状 `(N,)`，预期收益。
- `cov`: `np.ndarray`，形状 `(N, N)`，半正定协方差矩阵。
- `w_prev`: `np.ndarray`，形状 `(N,)`，当前组合权重。
- `lower`: `np.ndarray`，形状 `(N,)`，下界。
- `upper`: `np.ndarray`，形状 `(N,)`，上界。
- `sector_ids`: `np.ndarray`，形状 `(N,)`，每个资产所属行业 id。
- `sector_lower`: `dict[int, float]`，行业下界。
- `sector_upper`: `dict[int, float]`，行业上界。
- `factor_loadings`: `np.ndarray`，形状 `(N, K)`，资产对 K 个风险因子的暴露矩阵。
- `factor_lower`: `np.ndarray`，形状 `(K,)`，组合因子暴露下界。
- `factor_upper`: `np.ndarray`，形状 `(K,)`，组合因子暴露上界。
- `risk_aversion`: `float`，风险厌恶系数。
- `transaction_penalty`: `float`，交易惩罚系数。
- `turnover_limit`: `float`，L1 换手上限。

## 输出

返回 `dict`，至少包含：
- `weights`: `np.ndarray`，形状 `(N,)`。

其他字段评测器会忽略。

## 优化目标与约束

最大化：

`mu^T w - risk_aversion * w^T cov w - transaction_penalty * ||w - w_prev||_1`

约束：
- `sum(w) == 1`
- `lower_i <= w_i <= upper_i`
- 行业约束：
  - `sector_lower[s] <= sum_{i in sector s} w_i <= sector_upper[s]`
- 因子暴露约束：
  - `factor_lower[k] <= sum_i factor_loadings[i, k] * w_i <= factor_upper[k]`
- 换手约束：
  - `||w - w_prev||_1 <= turnover_limit`

## 预期结果

高质量解应满足：
- 数值容差内可行；
- 目标值尽量接近凸优化最优值。

## 计分方式

对每个测试实例：
1. 取参考最优目标值 `f_ref`（预先计算好的常量，见下文）。
2. **硬可行性门槛**：所有约束独立于目标函数重新校验，任一残差超过容差，该实例直接记 `0` 分：

   | 约束 | 残差 | 容差 |
   | --- | --- | --- |
   | 预算和 | `abs(sum(w) - 1)` | `1e-6` |
   | 逐资产上下界 | `max(lower - w, w - upper)` | `1e-6` |
   | 板块上下限 | 最大越界量 | `1e-5` |
   | 因子暴露 | 最大越界量 | `1e-5` |
   | 换手率 | `norm1(w - w_prev) - turnover_limit` | `1e-4` |

   不再有 `(1 - penalty)` 折扣，也没有部分得分：突破风险限额的组合本身不可交付，
   靠轻微超限换取目标值只会得 0 分，而不是仅损失几分。
3. 计算候选目标值 `f_cand`，对朴素锚点做归一化：
   - `f_anchor = min(f_uniform, f_prev_holdings)`
   - `norm = clip((f_cand - f_anchor) / (f_ref - f_anchor + 1e-12), 0, 1)`
4. 实例得分：`100 * norm`。

最终分数为所有实例的平均值。只有当每个实例都给出结构合法且可行的权重向量时，`valid` 才为 `1`。

## 候选程序的运行方式

`solve_instance(instance)` 在**独立子进程**中调用，只有权重向量会回传；目标值与全部约束
均由评测端自行重算。候选自报的任何分数字段都不会被采信，评测脚本的模块全局变量也不在
候选可达范围内。

## 理论上限

该问题是凸优化，参考实现（CVXPY 全局最优）可视为本任务定义下的理论上限，
对应得分 `100`。

## 实现建议

不依赖现成优化器的 baseline 可采用：
- 平滑目标 + 投影梯度上升；
- 迭代修复约束：
  - 先按个股上下界截断；
  - 再通过缩放 `w - w_prev` 控制换手；
  - 对行业超限做比例回收/补足；
  - 最后归一化到 `sum(w)=1`。

这种方法通常不是全局最优，但可作为可运行起点。

## 本仓库 Baseline 实现方式

- 文件：`baseline/init.py`
- 方法类型：一阶启发式（不调用外部优化器）
- 核心做法：
  - 对 L1 项做平滑后进行梯度上升，
  - 每轮迭代后对权重进行“修复/投影”，满足仓位边界、行业约束、换手与权重和约束。
- 特点：
  - 速度快、依赖少；
  - 不显式投影到因子暴露约束；
  - 不保证全局最优。

## 本仓库 Reference 实现方式

- 文件：`verification/reference.py`
- 方法类别：CVXPY 精确凸优化 / 整数规划
- 作用：用于生成归一化所需的参考目标值常量表。

> **候选不可见**：`verification/reference.py` 仅供维护者使用，已从 `agent_files.txt`
> 与 `copy_files.txt` 白名单中移除，评测脚本也不再 import 或执行它——它算出的参考值
> 已固化为 `verification/evaluate.py` 中的常量表（评测随机种子固定，可完全预计算）。
> 需要重算时执行 `python verification/evaluate.py --regenerate-reference-table`。
