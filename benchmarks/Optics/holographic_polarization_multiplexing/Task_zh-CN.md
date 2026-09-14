# 可微全息 H4 规范：偏振复用

## 工程背景

偏振复用的核心是：同一个光学器件，对不同偏振输入产生不同输出功能。

本任务要求：

- x 偏振输入输出图样 X，
- y 偏振输入输出图样 Y，
- 并且两通道串扰要低。

CS 类比：

- 一个共享模型，
- 两种输入模式，
- 模式条件下输出要可控且可分离。

应用：

- 偏振复用通信，
- 光学安全，
- 多功能衍射/超表面器件。

经济意义：

- 一个器件多功能，可减少硬件数量与系统集成成本。

## 你要做的事

改进 baseline，使其在“通道分离 + 目标配比 + 有效能量”上更好。

可编辑：

- `baseline/init.py`

通常只读：

- `verification/evaluate.py`
- `verification/reference_solver.py`

## 核心修改文件/函数

- `baseline/init.py`
- 核心函数：`solve(spec, device=None, seed=0)`

可以在同一文件内增删辅助函数，但必须保留文件底部的
`if __name__ == "__main__":` 块——它是评测入口。

## 程序如何被运行

你的文件会作为**独立进程**执行，工作目录是一个临时目录，其中只有两个文件：

- `problem.json`——以数据形式给出的题目（由评分器写入），
- `baseline/init.py` 的一份副本——你的程序。

候选进程无法访问任务目录、`verification/`、oracle 和评分脚本。
从当前目录读 `problem.json`，向当前目录写 `submission.npz`。

## 输入协议（`problem.json`）

题目定义由 `verification/problem_spec.py` 拥有，对所有提交完全一致。该文件只读，
并且在你的进程启动**之前**就已被评分器加载。

你会收到的字段：

- `shape`、`spacing`、`wavelength`、`waist_radius`、`layer_z`、`output_z`。
- `pattern_x_centers` / `pattern_x_ratios`——x 偏振输入应当形成的图案。
- `pattern_y_centers` / `pattern_y_ratios`——y 偏振输入对应的图案。
- `roi_radius_m`——统计功率的 ROI 半径。
- `steps`、`lr`——评分器给出的优化预算。
- 评分常数：`score_eff_target`、`score_ratio_scale`、`valid_*`。

`problem.json["submission"]` 会再次给出提交数组的准确名称、形状与取值范围。

## 输出协议（`submission.npz`）

只写**决策变量**——纯实数数组：

- `phase_x`：`float64`，形状 `(n_layers, shape, shape)`——按 `layer_z` 顺序给出每层
  Jones 矩阵 `[0,0]` 元的相位。
- `phase_y`：`float64`，同样形状——每层 Jones 矩阵 `[1,1]` 元的相位。

单位均为弧度，要求 `|phase| <= 1e4`。

可选、仅用于绘图诊断（不参与评分）：`loss_history`，一维浮点数组。

随后 `verification/evaluate.py` 自己完成以下全部工作：

1. 构建两路偏振高斯输入场；
2. 对每一层：先 `propagate_to_z(layer_z[i])`，再用
   `diag(exp(1j*phase_x[i]), exp(1j*phase_y[i]), 1)` 做 `polarized_modulate`；
3. 传播到 `output_z`；
4. 用 `pattern_*` 字段构建两张目标图；
5. 计算 match、separation、own-efficiency、比例误差与最终分数。

由此带来的设计约束：

- 返回 `system`、`input_field`、`target_field` 或自报的分数/指标**完全无效**——
  除上述数组外的任何内容都不会被读取。
- `submission.npz` 以 `allow_pickle=False` 加载，因此只有数组能通过。
- 数组会校验形状、dtype、有限性与取值范围。崩溃、超时、缺少 `submission.npz`
  或数组越界都是**硬拒绝**（`combined_score = -1e18`），而不是低分。

## Baseline 当前实现

baseline 目前刻意简化：

1. 构造 x/y 偏振输入高斯场。
2. 用对角 Jones 相位层（Ex、Ey 各自独立相位）。
3. 仅优化两通道归一化图像 MSE。

缺失项：

- 没有显式串扰项，
- 没有显式配比项，
- 没有显式目标通道效率项。

## Oracle 当前实现

`verification/reference_solver.py` 更强：

1. 分别为 x/y 目标生成 `slmsuite` WGS 相位种子。
2. 用种子初始化偏振相位层。
3. 复合目标微调：
   - 图样匹配，
   - 串扰抑制，
   - 配比约束，
   - 目标通道效率，
   - 相位平滑正则。

作为工程上更强对照。

## 指标与分数（0~1）

核心指标：

- `match_x`, `match_y`, `mean_match`：与目标图余弦相似度。
- `separation_x`, `separation_y`, `separation`：通道分离度。
- `own_efficiency`：能量落在目标通道 ROI 的比例。
- `ratio_mae_x`, `ratio_mae_y`, `mean_ratio_mae`：通道内配比误差。

派生分项：

- `ratio_score = exp(-mean_ratio_mae / score_ratio_scale)`
- `efficiency_score = min(1, own_efficiency / score_eff_target)`

最终分数：

- `score = (separation^0.55) * (ratio_score^0.20) * (efficiency_score^0.25) * (mean_match^0.05)`

解释：

- 该分数更强调“通道分离”和“目标通道有效能量”，
- 图样相似度仍有作用，但权重较小。

## valid 与 better 规则

`baseline valid=True` 需满足：

- `mean_match >= valid_match_min`
- `separation >= valid_separation_min`
- `score >= valid_score_min`

`reference better_than_baseline=True` 需满足：

- `reference_score >= baseline_score + better_score_margin`
- `reference_separation >= baseline_separation + better_sep_margin`

## 评测输出文件说明（artifacts）

输出目录：`verification/artifacts/`

- `summary.json`
  - 全量结构化结果（指标、分数、耗时、判定）。
- `polarization_maps.png`
  - x/y 两个输入通道的 target / baseline / reference 对比图。
- `loss_and_metrics.png`
  - 训练 loss 曲线，
  - 指标柱状图（`match`, `separation`, `ratio_score`, `score`）。

快速排查：

- match 还行但 separation 低：串扰问题，
- separation 高但 ratio_score 低：通道内配比分配不对，
- efficiency_score 低：目标 ROI 内有效能量不足。

## 运行方式

```bash
PY=python3
$PY benchmarks/Optics/holographic_polarization_multiplexing/verification/evaluate.py --device cpu
```

