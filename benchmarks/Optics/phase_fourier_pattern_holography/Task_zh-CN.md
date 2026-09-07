# 相位 DOE P2 说明：高难度 Fourier 图案全息

## 背景
这个任务本质是“有约束的图像重建”：
- 决策变量：相位图 `phase[y, x]`
- 前向模型：FFT 传播得到强度图
- 优化目标：既要重建稀疏高对比目标，也要保持暗区足够暗

从算法角度看，它是二维非凸逆问题。

## 你要做什么
改进 `baseline/init.py`，让输出强度图更接近目标结构，并减少暗区泄漏。

建议重点改：
- `solve(problem)` in `baseline/init.py`

## 可修改边界
- 可修改：`baseline/init.py`
- 只读（评测期间去写权限并做指纹校验）：`verification/validate.py`、`verification/problem.py`、`verification/metrics.py`、`frontier_eval/`

## 评分契约
评测器**不会 import** `baseline/init.py`。它会作为独立程序在单独子进程中运行，工作目录是一个
一次性临时目录，其中已经放好由评分侧生成的题目定义：

- `problem.json`——配置（`cfg`）以及 `decision_variable` 块，明确说明要返回什么
- `problem.npz`——`x`, `y`, `aperture_amp`, `target_amp`

你的程序必须在当前目录写出 `submission.json` 并以 0 退出：

```json
{"phase": [[...128 floats...], ...]}   // 128 rows, radians
```

评测器对 `phase` 的强制校验：
- 形状必须是 `(128, 128)`
- 每个元素有限，且 `|phase| <= 1e4`

`target_amp` 由评分侧生成并只读下发。它就是你被评判的目标，你无法替换成自己的目标。

**只返回决策变量，不要返回别的。** 其它任何键——`metrics`、`score`、`score_pct`、
`cv_orders` ……——都会在评分前被丢弃，仅记录在指标文件的 `contract.ignored_submission_keys` 里。
题目定义、前向模型与全部指标现在都在 `verification/problem.py` 与 `verification/metrics.py`：
评测器自己重建题目、自己对你的决策变量跑前向、自己重算所有指标。你自报的任何数字都无法改变分数，
且 oracle 使用完全相同的函数打分。

提交被拒（形状/长度错误、非有限值或越界、非零退出码、超时、没有 `submission.json`）即判为 invalid。

## Baseline 当前实现
当前 baseline 是单次逆变换：
1. 给目标振幅附加随机相位
2. 只做一次逆 FFT
3. 结果相位直接作为全息图

速度快，但在稀疏高对比场景下能力有限。

## Oracle 当前实现
oracle 使用 `slmsuite` 迭代加权 GS：
- `Hologram.optimize(method="WGS-Kim")`
- 通过迭代修正幅度/相位

通常能显著提升重建质量与暗区控制。

## 指标与分数（越高越好）
评测指标：
- `nmse`：预测强度与目标强度的归一化 RMSE
- `energy_in_target`：`target_amp > 0.30` 区域的能量占比
- `dark_suppression`：暗区抑制度，定义为 `1 - leak`，其中 leak 是 `target_amp < 0.03` 区域能量占比

分数公式：
- `pattern_score = clip(1 - nmse / 4.0, 0, 1)`
- `energy_score = clip((energy_in_target - 0.10) / (0.70 - 0.10), 0, 1)`
- `dark_score = clip((dark_suppression - 0.35) / (0.90 - 0.35), 0, 1)`
- `score_pct = 100 * (0.55*pattern_score + 0.30*energy_score + 0.15*dark_score)`

范围：`0 ~ 100`，越高越好。

## valid 判定
baseline 满足以下条件则 valid：
- `score_pct >= 20`
- `energy_in_target >= 0.45`
- `dark_suppression >= 0.60`

## 可行优化方向
常见有效策略：
- 迭代相位检索替代单次逆变换
- 针对稀疏目标做区域加权
- 对暗区泄漏引入显式惩罚
- 改进初始化与迭代调度

