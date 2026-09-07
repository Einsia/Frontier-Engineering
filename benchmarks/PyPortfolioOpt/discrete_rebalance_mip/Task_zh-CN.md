# 任务 03 说明：离散再平衡 MIP

## 背景

你的模型给出目标权重，但实际执行必须用整数手数下单。
同时还要满足交易费与换手金额限制。

这本质上是一个混合整数线性优化问题。

## 输入

`instance` 字段：
- `prices`: `np.ndarray`，形状 `(N,)`
- `lot_sizes`: `np.ndarray`，形状 `(N,)`，正整数
- `current_lots`: `np.ndarray`，形状 `(N,)`，当前整数手数
- `target_weights`: `np.ndarray`，形状 `(N,)`，和接近 1
- `portfolio_value`: `float`，最终持仓 + 手续费预算
- `fee_rate`: `float`，按成交金额收取比例费用
- `turnover_limit_value`: `float`，成交金额上限
- `max_lots`: `np.ndarray`，形状 `(N,)`，每个资产最大手数

定义每手金额：`unit_i = prices_i * lot_sizes_i`。

## 输出

返回：
- `lots`: `np.ndarray`，形状 `(N,)`，最终整数手数

其他字段评测器忽略。

## 优化目标与约束

最小化：

`sum_i |unit_i * lots_i - target_weights_i * portfolio_value| + fee_rate * traded_notional`

其中：

`traded_notional = sum_i unit_i * |lots_i - current_lots_i|`

约束：
- `0 <= lots_i <= max_lots_i`，且为整数
- `traded_notional <= turnover_limit_value`
- `sum_i unit_i * lots_i + fee_rate * traded_notional <= portfolio_value`

## 预期结果

高质量解应在可执行约束下尽量贴近目标权重（金额层面）。

## 计分方式

对每个实例：
1. 取参考整数最优目标值 `obj_ref`（预先计算好的常量，见下文）。
2. **硬可行性门槛**：所有约束独立于目标函数重新校验，任一残差超过容差，该实例直接记 `0` 分：

   | 约束 | 残差 | 容差 |
   | --- | --- | --- |
   | 整数性 | `abs(lots - round(lots))` | `1e-6` |
   | 手数上下界 | `max(-lots, lots - max_lots)` | `1e-6` |
   | 换手名义额 | `traded_notional - turnover_limit_value` | `1e-6 + 1e-9 * limit` |
   | 预算 | `spend - portfolio_value` | `1e-6 + 1e-9 * portfolio_value` |

   不再有 `(1 - penalty)` 折扣，也没有部分得分。本题尤其关键：忽略换手上限的下单方案
   目标值反而**低于**真正的整数最优解，在软罚机制下一份根本无法执行的委托单仍能拿分。
3. 计算候选目标值 `obj_cand`，以不交易为锚点归一化：
   - `obj_anchor = objective(current_lots)`
   - `norm = clip((obj_anchor - obj_cand) / (obj_anchor - obj_ref + 1e-12), 0, 1)`
4. 实例得分：`100 * norm`。

最终分数为所有实例的平均值。只有当每个实例都给出结构合法且可行的手数向量时，`valid` 才为 `1`。

## 候选程序的运行方式

`solve_instance(instance)` 在**独立子进程**中调用，只有手数向量会回传；目标值与全部约束
均由评测端自行重算。候选自报的任何分数字段都不会被采信，评测脚本的模块全局变量也不在
候选可达范围内。

## 理论边界

- 实际评测上限：参考整数最优（100 分）。
- 额外理论对照：LP 松弛下界（连续手数），评测脚本会同时输出用于分析整数间隙。

## 实现建议

不调用外部求解器时可采用：
- 按目标金额四舍五入初始化；
- 对预算/换手超限做修复循环；
- 通过 `+/-1` 手局部搜索改进目标；
- 在约束允许下贪心补足低配资产。

这是实务里常见的启发式工程方案。

## 本仓库 Reference 实现方式

- 文件：`verification/reference.py`
- 方法类别：CVXPY 精确凸优化 / 整数规划
- 作用：用于生成归一化所需的参考目标值常量表。

> **候选不可见**：`verification/reference.py` 仅供维护者使用，已从 `agent_files.txt`
> 与 `copy_files.txt` 白名单中移除，评测脚本也不再 import 或执行它——它算出的参考值
> 已固化为 `verification/evaluate.py` 中的常量表（评测随机种子固定，可完全预计算）。
> 需要重算时执行 `python verification/evaluate.py --regenerate-reference-table`。
