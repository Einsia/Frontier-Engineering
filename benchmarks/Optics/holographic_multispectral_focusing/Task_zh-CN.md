# 可微全息 H3 规范：多波长聚焦/分束

## 工程背景

不同波长（可理解为不同颜色）传播行为不同。

很多真实系统要求“同一个器件”同时满足多波长目标：

- 每个波长到自己的空间位置，
- 多波长总体功率分配要满足指定比例。

从 CS 角度看，这是多域联合优化：

- 域 = 波长，
- 每个域有自己的空间目标，
- 还有全局耦合约束（光谱比例）。

应用：

- 彩色成像光学，
- WDM 波分路由，
- 色差补偿。

经济意义：

- 多波长性能更好，可在不增加硬件通道的前提下提升成像/传输品质。

## 你要做的事

改进 `baseline/init.py` 的优化流程，在共享硬件约束下提升分数。

可编辑：

- `baseline/init.py`

挑战中通常只读：

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

除此之外什么都访问不到：任务目录、`verification/`、oracle 和评分脚本都不存在，
也无法 import。你从当前目录读 `problem.json`，向当前目录写 `submission.npz`。

## 输入协议（`problem.json`）

题目定义由 `verification/problem_spec.py` 拥有，对所有提交完全一致。该文件只读，
并且在你的进程启动**之前**就已被评分器加载。

你会收到的字段：

- `shape`、`spacing`、`waist_radius`、`layer_z`、`output_z`——几何配置。
- `wavelengths`——共享同一套硬件的四个波长。
- `refractive_index`——介质的（常数）折射率 `n`。
- `target_centers`——每个波长各一个目标坐标。
- `target_spectral_ratios`——期望的波长间功率分配比例。
- `roi_radius_m`——统计能量的 ROI 半径。
- `steps`、`lr`、`init_thickness_mean`、`init_thickness_std`、`num_restarts`——
  评分器给出的优化预算。
- 评分常数：`score_eff_target`、`score_spectral_scale`、`valid_*`。

`problem.json["submission"]` 会再次给出提交数组的准确名称、形状与取值范围。

## 输出协议（`submission.npz`）

只写**决策变量**——纯实数数组：

- `thickness`：`float64`，形状 `(n_layers, shape, shape)`——按 `layer_z` 顺序给出每层
  的**物理厚度**，单位米，取值范围 `[0, max_thickness_m]`。

决策变量是厚度而非相位，因为同一条物理厚度分布对不同波长会产生**不同**的相位

    phi(x, y; lambda) = 2*pi/lambda * (n - 1) * t(x, y)

正是这一点使本题成为"共享硬件"问题，而不是四个互相独立的单波长全息图。

可选、仅用于绘图诊断（不参与评分）：`loss_history`，一维浮点数组。

随后 `verification/evaluate.py` 自己完成以下全部工作：

1. 用你的 `thickness` 构建色散的 `PolychromaticPhaseModulator` 堆叠；
2. 为每个波长构建高斯输入场；
3. 将它们分别传播到 `output_z`；
4. 计算逐波长的效率、串扰与形状余弦；
5. 计算光谱比例误差与最终分数。

`verification/reference_solver.py` 中的 oracle 被**有意**允许使用逐波长独立的相位掩模
（相当于四个独立全息图）。这是评分器选定的上界放宽，会在 `summary.json` 的
`reference.design_space` 中标注，提交方不可使用。

由此带来的设计约束：

- 返回 `system`、`input_field`、`target_field` 或自报的分数/指标**完全无效**——
  除上述数组外的任何内容都不会被读取。
- `submission.npz` 以 `allow_pickle=False` 加载，因此只有数组能通过。
- 数组会校验形状、dtype、有限性与取值范围。崩溃、超时、缺少 `submission.npz`
  或数组越界都是**硬拒绝**（`combined_score = -1e18`），而不是低分。

## Baseline 当前实现

baseline 目前刻意简化：

1. 构造共享多波长相位系统。
2. 每个波长只优化目标 ROI 效率。
3. 各波长损失取平均。

刻意缺失：

- 不显式抑制串扰，
- 不显式约束光谱比例，
- 无高级初始化。

## Oracle 当前实现

reference 更强，且硬件约束更宽松：

1. 每个波长用 `slmsuite` WGS 生成相位初值。
2. 构建两个候选：
   - 直接按波长独立相位执行，
   - 按波长独立相位再微调。
3. 选任务分数更高的候选。

因为允许波长特定相位（而非严格共享掩模），它是上界对照解。

## 指标与分数（0~1）

每个波长 `i`：

- `target_efficiency_i = P_target_i / P_total_i`
- `designated_crosstalk_i = P_other_designated_i / (P_target_i + P_other_designated_i)`
- `shape_cosine_i = cosine(I_pred_norm_i, I_target_norm_i)`

全局：

- `mean_target_efficiency`
- `mean_crosstalk`
- `mean_shape_cosine`
- `spectral_ratio_mae`

派生分项：

- `efficiency_score = min(1, mean_target_efficiency / score_eff_target)`
- `isolation_score = 1 - mean_crosstalk`
- `spectral_score = exp(-spectral_ratio_mae / score_spectral_scale)`

最终分数：

- `mean_score = (efficiency_score^0.45) * (isolation_score^0.25) * (spectral_score^0.20) * (mean_shape_cosine^0.10)`

解释：

- 高分必须同时满足空间目标和光谱目标，
- 单一维度很好、另一维度很差，最终也拿不到高分。

## valid 与 better 规则

`baseline valid=True` 需满足：

- `mean_target_efficiency >= valid_mean_target_efficiency_min`
- `mean_crosstalk <= valid_mean_crosstalk_max`
- `mean_score >= valid_mean_score_min`

`reference better_than_baseline=True` 需满足：

- `reference_mean_score >= baseline_mean_score + better_score_margin`
- `reference_mean_shape_cosine >= baseline_mean_shape_cosine + better_shape_margin`

## 评测输出文件说明（artifacts）

输出目录：`verification/artifacts/`

- `summary.json`
  - 完整指标、分数、耗时、判定结果。
- `spectral_intensity_maps.png`
  - 每个波长的 target / baseline / reference 强度图。
- `loss_and_spectral_ratios.png`
  - 训练 loss 曲线，
  - 光谱比例柱状图（目标 vs baseline vs reference）。

排查建议：

- 光谱比例差：加强 ratio/spectral loss，
- 串扰高：加强 designated-vs-other 抑制项，
- shape cosine 低：改初始化或优化权重平衡。

## 运行方式

```bash
PY=python3
$PY benchmarks/Optics/holographic_multispectral_focusing/verification/evaluate.py --device cpu
```

