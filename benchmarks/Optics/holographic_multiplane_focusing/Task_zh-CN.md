# 可微全息 H2 规范：多平面同时聚焦

## 工程背景

任务1是单平面。任务2引入了**深度维度**。

你需要一个统一的光学系统，在多个 `z` 距离上同时满足不同目标图样：

- 硬件参数相同，
- 不同深度有不同目标焦点和配比。

可类比为“一个模型同时服务多个切片视图”。

应用场景：

- 3D 光镊，
- 体加工，
- 多深度投影。

经济意义：

- 一个器件完成多深度功能，可降低系统复杂度与标定成本。

## 你要做的事

改进 baseline 的优化流程，让它在多平面指标上更好。

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

- `shape`、`spacing`、`wavelength`、`waist_radius`、`layer_z`——共享的相位面堆叠。
- `planes`——各观测面配置的列表，每项包含 `z`、`centers`、`ratios`。
- `roi_radius_m`——统计单个光斑功率的 ROI 半径。
- `steps`、`lr`——评分器给出的优化预算。
- 评分常数：`score_eff_target`、`score_ratio_scale`、`valid_*`。

`problem.json["submission"]` 会再次给出提交数组的准确名称、形状与取值范围。

## 输出协议（`submission.npz`）

只写**决策变量**——纯实数数组：

- `phases`：`float64`，形状 `(n_layers, shape, shape)`——按 `layer_z` 顺序给出每层
  `PhaseModulator` 的相位图。单位弧度，要求 `|phase| <= 1e4`。

同一套堆叠必须同时服务 `planes` 中的所有观测面，不存在逐面独立的掩模。

可选、仅用于绘图诊断（不参与评分）：`loss_history`，一维浮点数组。

随后 `verification/evaluate.py` 自己完成以下全部工作：

1. 用你的 `phases` 构建 `PhaseModulator` 光学系统；
2. 构建高斯输入场；
3. 传播到 `planes` 中的每个 `z`；
4. 用各面的 `centers` / `ratios` 构建该面的目标场；
5. 计算逐面的 `ratio_mae`、`efficiency`、`shape_cosine` 及平均分。

由此带来的设计约束：

- 返回 `system`、`input_field`、`target_field` 或自报的分数/指标**完全无效**——
  除上述数组外的任何内容都不会被读取。
- `submission.npz` 以 `allow_pickle=False` 加载，因此只有数组能通过。
- 数组会校验形状、dtype、有限性与取值范围。崩溃、超时、缺少 `submission.npz`
  或数组越界都是**硬拒绝**（`combined_score = -1e18`），而不是低分。

## Baseline 当前实现

baseline 目前刻意偏弱：

1. 构造一个输入高斯场。
2. 为每个平面构造目标场。
3. 计算各平面重叠损失。
4. 平均后用 Adam 优化。

不足：

- 不直接优化配比，
- 不直接控制泄露/效率，
- 没有针对困难平面的动态加权。

## Oracle 当前实现

`verification/reference_solver.py` 更强：

1. 每个平面先用 `slmsuite` WGS 生成相位种子。
2. 将多个种子融合成多层初值。
3. 用复合目标微调：
   - 重叠项，
   - 配比项，
   - 泄露项。
4. 对困难平面动态加权。

该实现作为对照上界。

## 指标与分数（0~1）

对每个平面 `m` 计算：

- `ratio_mae_m`
- `efficiency_m = P_focus_m / P_total_m`
- `shape_cosine_m = cosine(I_pred_norm_m, I_target_norm_m)`

派生分项：

- `ratio_score_m = exp(-ratio_mae_m / score_ratio_scale)`
- `efficiency_score_m = min(1, efficiency_m / score_eff_target)`

平面分数：

- `score_m = (efficiency_score_m^0.50) * (ratio_score_m^0.35) * (shape_cosine_m^0.15)`

全局：

- `mean_ratio_mae`
- `mean_efficiency`
- `mean_shape_cosine`
- `mean_score = average(score_m)`

解释：

- 越接近 `1` 表示多平面同时满足得更好，
- 低分通常意味着某个平面严重拖后腿。

## valid 与 better 规则

`baseline valid=True` 需同时满足：

- `mean_ratio_mae <= valid_mean_ratio_mae_max`
- `mean_efficiency >= valid_mean_efficiency_min`
- `mean_score >= valid_mean_score_min`

`reference better_than_baseline=True` 需同时满足：

- `reference_mean_score >= baseline_mean_score + better_score_margin`
- `reference_mean_shape_cosine >= baseline_mean_shape_cosine + better_shape_margin`

## 评测输出文件说明（artifacts）

输出目录：`verification/artifacts/`

- `summary.json`
  - 完整指标、配置、耗时、valid 与对比结论。
- `plane_intensity_maps.png`
  - 每个平面展示 target / baseline / reference 图。
- `loss_and_efficiency.png`
  - 训练损失曲线 + 各平面效率柱状图。

快速定位问题：

- 位置对但配比差：强化 ratio loss，
- 多平面都暗：强化能量集中/泄露控制，
- 只有一个平面差：做平面级加权或分阶段训练。

## 运行方式

```bash
PY=python3
$PY benchmarks/Optics/holographic_multiplane_focusing/verification/evaluate.py --device cpu
```

