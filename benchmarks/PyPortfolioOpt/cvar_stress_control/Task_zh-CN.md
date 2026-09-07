# 任务 02 说明：CVaR 压力控制配置

## 背景

你要在情景收益数据上做多头资产配置。
PM 要求组合达到最低预期收益，风控要求控制尾部亏损，因此目标是：
在约束下最小化 CVaR。

## 输入

`instance` 字段：
- `scenario_returns`: `np.ndarray`，形状 `(T, N)`
- `mu`: `np.ndarray`，形状 `(N,)`，预期收益估计
- `w_prev`: `np.ndarray`，形状 `(N,)`
- `lower`: `np.ndarray`，形状 `(N,)`
- `upper`: `np.ndarray`，形状 `(N,)`
- `sector_ids`: `np.ndarray`，形状 `(N,)`
- `sector_lower`: `dict[int, float]`
- `sector_upper`: `dict[int, float]`
- `beta`: `float`，CVaR 置信度
- `target_return`: `float`，最低收益门槛
- `turnover_limit`: `float`，`||w - w_prev||_1` 上限

## 输出

返回：
- `weights`: `np.ndarray`，形状 `(N,)`

## 优化目标与约束

最小化场景损失的 CVaR：
- 第 `t` 个场景损失：`L_t = -R_t^T w`
- `CVaR_beta = alpha + 1/((1-beta)T) * sum_t u_t`
- 且 `u_t >= L_t - alpha`，`u_t >= 0`

约束：
- `sum(w) == 1`
- `lower_i <= w_i <= upper_i`
- `mu^T w >= target_return`
- 行业上下界约束
- `||w - w_prev||_1 <= turnover_limit`

## 预期结果

高质量解应在满足约束前提下，把尾部风险压到接近最优。

## 计分方式

对每个实例：
1. 取参考最优 CVaR `c_ref`（预先计算好的常量，见下文）。
2. **硬可行性门槛**：所有约束独立于目标函数重新校验，任一残差超过容差，该实例直接记 `0` 分：

   | 约束 | 残差 | 容差 |
   | --- | --- | --- |
   | 预算和 | `abs(sum(w) - 1)` | `1e-6` |
   | 逐资产上下界 | `max(lower - w, w - upper)` | `1e-6` |
   | 板块上下限 | 最大越界量 | `1e-5` |
   | 换手率 | `norm1(w - w_prev) - turnover_limit` | `1e-4` |
   | 收益下限 | `target_return - mu @ w` | `1e-8 + 1e-4 * target_return` |

   不再有 `(1 - penalty)` 折扣，也没有部分得分：达不到规定收益或突破暴露限额的组合
   本身不可交付，靠越界压低 CVaR 只会得 0 分。
3. 计算候选 CVaR `c_cand` 并归一化：
   - `c_anchor = max(CVaR(uniform), CVaR(w_prev))`
   - `norm = clip((c_anchor - c_cand) / (c_anchor - c_ref + 1e-12), 0, 1)`
4. 实例得分：`100 * norm`。

最终分数为所有实例的平均值。只有当每个实例都给出结构合法且可行的权重向量时，`valid` 才为 `1`。

## 候选程序的运行方式

`solve_instance(instance)` 在**独立子进程**中调用，只有权重向量会回传；CVaR 与全部约束
均由评测端自行重算。候选自报的任何分数字段都不会被采信，评测脚本的模块全局变量也不在
候选可达范围内。

## 理论上限

该形式是凸优化，参考实现（CVXPY）给出的最优值可视为本任务定义下理论上限，
对应得分 100。

## 实现建议

不调用现成优化器时可从启发式出发：
- 用最差场景估计单资产尾部风险；
- 构造 `mu / tail_risk` 风险收益打分；
- 生成初始权重并做约束修复；
- 若未达到收益门槛，贪心向高收益资产挪仓。

该方法不是全局最优，但足够用于 baseline。

## 本仓库 Reference 实现方式

- 文件：`verification/reference.py`
- 方法类别：CVXPY 精确凸优化 / 整数规划
- 作用：用于生成归一化所需的参考目标值常量表。

> **候选不可见**：`verification/reference.py` 仅供维护者使用，已从 `agent_files.txt`
> 与 `copy_files.txt` 白名单中移除，评测脚本也不再 import 或执行它——它算出的参考值
> 已固化为 `verification/evaluate.py` 中的常量表（评测随机种子固定，可完全预计算）。
> 需要重算时执行 `python verification/evaluate.py --regenerate-reference-table`。
