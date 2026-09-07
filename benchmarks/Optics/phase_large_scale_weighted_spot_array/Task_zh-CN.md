# 相位 DOE P4 说明：大规模加权焦点阵列

## 背景
这个任务是“多目标能量分配”问题：
- 决策变量：相位矩阵 `(N, N)`
- 前向模型：Fourier 传播
- 目标：在 8x8 大规模焦点阵列上满足加权配光

相比 Task01，这题目标数量更多、分布更广。

## 你要做什么
改进 baseline 相位生成逻辑，提高大规模焦点阵列质量。

主要修改函数：
- `solve(problem)` in `baseline/init.py`

## 可修改边界
- 可修改：`baseline/init.py`
- 只读（评测期间去写权限并做指纹校验）：`verification/validate.py`、`verification/problem.py`、`verification/metrics.py`、`frontier_eval/`

## 评分契约
评测器**不会 import** `baseline/init.py`。它会作为独立程序在单独子进程中运行，工作目录是一个
一次性临时目录，其中已经放好由评分侧生成的题目定义：

- `problem.json`——配置（`cfg`）以及 `decision_variable` 块，明确说明要返回什么
- `problem.npz`——`x`, `y`, `spots`, `weights`, `aperture_amp`

你的程序必须在当前目录写出 `submission.json` 并以 0 退出：

```json
{"phase": [[...128 floats...], ...]}   // 128 rows, radians
```

评测器对 `phase` 的强制校验：
- 形状必须是 `(128, 128)`
- 每个元素有限，且 `|phase| <= 1e4`

**只返回决策变量，不要返回别的。** 其它任何键——`metrics`、`score`、`score_pct`、
`cv_orders` ……——都会在评分前被丢弃，仅记录在指标文件的 `contract.ignored_submission_keys` 里。
题目定义、前向模型与全部指标现在都在 `verification/problem.py` 与 `verification/metrics.py`：
评测器自己重建题目、自己对你的决策变量跑前向、自己重算所有指标。你自报的任何数字都无法改变分数，
且 oracle 使用完全相同的函数打分。

提交被拒（形状/长度错误、非有限值或越界、非零退出码、超时、没有 `submission.json`）即判为 invalid。

## Baseline 当前实现
baseline 使用非迭代的加权平面波叠加，然后直接取相位。

## Oracle 当前实现
oracle 使用 `slmsuite` 的迭代 WGS：
- `Hologram.optimize(method="WGS-Kim")`

## 指标与分数（越高越好）
原始指标：
- `ratio_mae`
- `cv_spots`
- `efficiency`

分数公式：
- `ratio_score = clip(1 - ratio_mae / 0.03, 0, 1)`
- `uniform_score = clip(1 - cv_spots / 1.40, 0, 1)`
- `efficiency_score = clip((efficiency - 0.40) / (0.90 - 0.40), 0, 1)`
- `score_pct = 100 * (0.45*ratio_score + 0.35*uniform_score + 0.20*efficiency_score)`

范围：`0 ~ 100`，越高越好。

## valid 判定
- `score_pct >= 20`
- `ratio_mae <= 0.03`
- `cv_spots <= 1.40`
- `efficiency >= 0.50`

## 可行优化方向
- 迭代权重修正（替代一次性相位）
- 局部相位细化或分块更新
- 动态平衡配光误差与效率

