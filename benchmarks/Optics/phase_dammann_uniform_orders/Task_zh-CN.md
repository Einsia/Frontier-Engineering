# 相位 DOE P3 说明：Dammann 均匀级次

## 背景
这是一个**参数优化问题**。
你要优化一维向量 `transitions`（单周期内二值相位切换位置），并通过仿真器评估结果。

可视为：
- 决策变量：`transitions`（连续向量）
- 仿真器：`diffractio` 传播流程
- 目标：让指定衍射级次更均匀且效率更高

## 你要做什么
改进 baseline 的跃迁位置生成策略。

主要优化点：
- `solve(problem)` in `baseline/init.py`

`main()` 把返回的向量写入 `submission.json`。评测器负责构场、传播和指标计算。

## 可修改边界
- 可修改：`baseline/init.py`
- 只读（评测期间去写权限并做指纹校验）：`verification/validate.py`、`verification/problem.py`、`verification/metrics.py`、`frontier_eval/`

## 评分契约
评测器**不会 import** `baseline/init.py`。它会作为独立程序在单独子进程中运行，工作目录是一个
一次性临时目录，其中已经放好由评分侧生成的题目定义：

- `problem.json`——配置（`cfg`）以及 `decision_variable` 块，明确说明要返回什么
- `problem.npz`——`x_period`

你的程序必须在当前目录写出 `submission.json` 并以 0 退出：

```json
{"transitions": [t0, t1, ..., t13]}   // micrometres
```

评测器对 `transitions` 的强制校验：
- 恰好 `cfg["num_transitions"]`（14）个数
- **严格单调递增**
- 每个元素有限，且落在 `[-period_size/2, +period_size/2]` 内

**只返回决策变量，不要返回别的。** 其它任何键——`metrics`、`score`、`score_pct`、
`cv_orders` ……——都会在评分前被丢弃，仅记录在指标文件的 `contract.ignored_submission_keys` 里。
题目定义、前向模型与全部指标位于 `verification/problem.py` 与 `verification/metrics.py`：
评测器根据提交的决策变量运行前向模型并计算指标；oracle 使用相同的计分函数。

提交被拒（形状/长度错误、非有限值或越界、非零退出码、超时、没有 `submission.json`）即判为 invalid。

## Baseline 当前实现
当前 baseline 在固定边界内取均匀间隔跃迁。下面 1-5 步由评测器的前向模型
（`verification/metrics.py`）执行：
1. 生成单周期二值相位掩膜
2. 重复周期构造完整光栅
3. 叠加透镜相位
4. 用 `RS` 传播到焦面
5. 在每个级次窗口积分能量

## Oracle 当前实现
评测会计算两个强参考并取高分：
1. 文献跃迁表（diffractio Dammann 示例）
2. SciPy 差分进化（`scipy.optimize.differential_evolution`）

最终 oracle：`best_of_literature_and_scipy_de`。

## 指标与分数（越高越好）
原始指标：
- `cv_orders`（越小越好）
- `efficiency`（越大越好）
- `min_to_max`（越大越好）

分数公式：
- `uniform_score = clip(1 - cv_orders / 0.9, 0, 1)`
- `efficiency_score = clip((efficiency - 0.003) / (0.18 - 0.003), 0, 1)`
- `balance_score = clip((min_to_max - 0.15) / (0.90 - 0.15), 0, 1)`
- `score_pct = 100 * (0.60*uniform_score + 0.30*efficiency_score + 0.10*balance_score)`

范围：`0 ~ 100`，越高越好。

## valid 判定
- `cv_orders <= 0.8`
- `efficiency >= 0.003`
- `min_to_max >= 0.15`

## 可行优化方向
- 在跃迁向量上做约束优化
- 利用对称性降低维度
- 在均匀性与效率之间做权衡
- 加最小间距约束提升可制造性

