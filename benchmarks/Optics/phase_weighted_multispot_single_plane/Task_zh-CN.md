# 相位 DOE P1 说明：高难度加权多焦点

## 背景
你可以把这个任务理解为一个 **二维数组优化问题**：
- 输入：相位矩阵 `phase[y, x]`
- 前向黑盒：`phase -> 远场强度图`
- 目标：让很多目标焦点按给定比例分配能量

光学上是纯相位 Fourier 全息；算法上是非凸优化问题。

## 你要做什么
改进 `baseline/init.py`，让生成的相位图在“稠密、多目标、非均匀配光”场景下取得更高分。

建议主要修改：
- `solve(problem)` in `baseline/init.py`

可以在同文件中增加辅助函数；唯一固定的契约是下面的 `submission.json` 格式。

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
当前 baseline 是有意简化的：
1. 每个目标焦点构造一个复平面波项
2. 按权重做相干叠加
3. 取叠加结果的相位作为输出相位图

优点是快；缺点是不迭代，面对稠密非均匀目标容易失配。

## Oracle 当前实现
评测内置 oracle 使用 `slmsuite` 的加权 GS：
- `Hologram.optimize(method="WGS-Kim")`
- 通过迭代更新来逼近目标配光

因此 oracle 是强迭代方法，baseline 是弱非迭代方法。

## 指标与分数（越高越好）
评测计算：
- `ratio_mae`：实际焦点比例与目标比例的平均绝对误差（越小越好）
- `cv_spots`：焦点能量变异系数（越小越好）
- `efficiency`：目标窗口总能量占比（越大越好）
- `min_peak_ratio`：最弱峰 / 最强峰（越大越好）

分数公式：
- `ratio_score = clip(1 - ratio_mae / 0.07, 0, 1)`
- `uniform_score = 1 / (1 + (cv_spots / 0.85)^2)`
- `efficiency_score = clip((efficiency - 0.15) / (0.80 - 0.15), 0, 1)`
- `peak_score = clip((min_peak_ratio - 0.003) / (0.20 - 0.003), 0, 1)`
- `score = 0.25*ratio_score + 0.45*uniform_score + 0.20*efficiency_score + 0.10*peak_score`
- `score_pct = 100 * score`（兼容字段）

范围：`0 ~ 1`，越高越好。

## valid 判定
baseline 同时满足以下条件才算 valid：
- `score >= 0.20`
- `efficiency >= 0.45`
- `min_peak_ratio > 0`

## 可行优化方向
常见有效改法：
- GS/WGS 类迭代相位检索
- 按焦点误差做反馈修正
- 加阻尼或正则提高稳定性
- 更好的初始化（优于直接叠加）
