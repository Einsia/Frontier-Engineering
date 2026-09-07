# 可微全息 H1 规范：多焦点相对光强配比控制

## 工程背景

你可以把这个任务理解为“物理版图像生成器”：

- 输入：一束激光（2D 场）。
- 可训练参数：若干相位掩模层。
- 输出：某个观测平面的强度图。

目标是：在输出面上形成 **6 个亮点**，且亮点之间的相对亮度满足指定比例。

工程意义：

- 并行激光加工（一次打多个点），
- 光镊多陷阱控制，
- 多通道光耦合。

经济价值：

- 更高能量利用率和更准的分配，可提升产线效率与良率。

## 你要做的事

你需要改进 baseline 的优化策略，使其分数更高。

任务约束：

- 允许修改：`baseline/init.py`
- `verification/` 下评测和 oracle 视为只读。

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

- `shape`、`spacing`、`wavelength`、`waist_radius`——网格与光源。
- `layer_z`——每层可训练相位面的 z 位置。
- `output_z`——观测面。
- `focus_centers`——6 个目标光斑坐标 `(x, y)`，单位米。
- `focus_ratios`——各光斑的目标相对功率。
- `roi_radius_m`——统计单个光斑功率的 ROI 半径。
- `steps`、`lr`——评分器给出的优化预算。
- 评分常数：`score_eff_target`、`score_ratio_scale`、`valid_*`。

`problem.json["submission"]` 会再次给出提交数组的准确名称、形状与取值范围。

## 输出协议（`submission.npz`）

只写**决策变量**——纯实数数组：

- `phases`：`float64`，形状 `(n_layers, shape, shape)`——按 `layer_z` 顺序给出每层
  `PhaseModulator` 的相位图。单位弧度，要求 `|phase| <= 1e4`。

可选、仅用于绘图诊断（不参与评分）：`loss_history`，一维浮点数组。

随后 `verification/evaluate.py` 自己完成以下全部工作：

1. 用你的 `phases` 构建 `PhaseModulator` 光学系统；
2. 构建高斯输入场；
3. 传播到 `output_z`；
4. 用 `focus_centers` / `focus_ratios` 构建目标场；
5. 计算 `ratio_mae`、`efficiency`、`shape_cosine` 与最终分数。

由此带来的设计约束：

- 返回 `system`、`input_field`、`target_field` 或自报的分数/指标**完全无效**——
  除上述数组外的任何内容都不会被读取。
- `submission.npz` 以 `allow_pickle=False` 加载，因此只有数组能通过。
- 数组会校验形状、dtype、有限性与取值范围。崩溃、超时、缺少 `submission.npz`
  或数组越界都是**硬拒绝**（`combined_score = -1e18`），而不是低分。

## Baseline 当前实现

当前 baseline 有意简化：

1. 构造高斯输入光。
2. 用 6 个高斯斑点（按目标比例加权）构造目标场。
3. 只优化重叠损失：
   - `loss = 1 - |<output, target>|^2`
4. Adam 固定步数训练。

设计弱点：

- 没有直接优化配比误差，
- 没有显式惩罚泄露，
- 没有分阶段优化策略。

## Oracle 当前实现

`verification/reference_solver.py` 更强，允许第三方库：

1. 先用 `slmsuite` 的 WGS 生成高质量相位初值。
2. 将初值注入系统层。
3. 用复合目标微调：
   - 重叠项，
   - 配比误差项，
   - 泄露项，
   - 相位平滑正则。

它是工程上更强的参考解，不是 baseline。

## 指标与分数（0~1，越高越好）

在输出强度上计算：

- `ratio_mae`：焦点配比 MAE。
- `efficiency`：所有焦点 ROI 内能量占总能量比例。
- `shape_cosine`：预测与目标归一化强度图余弦相似度。

派生分项：

- `ratio_score = exp(-ratio_mae / score_ratio_scale)`
- `efficiency_score = min(1, efficiency / score_eff_target)`

最终分数：

- `score = (efficiency_score^0.58) * (ratio_score^0.22) * (shape_cosine^0.20)`

解释：

- 接近 `1.0`：效率高、配比准、形状像目标；
- `0.2~0.4`：部分可用，但明显有短板；
- 接近 `0`：基本没有实现目标。

## valid 与 better 规则

`baseline valid=True` 需要同时满足：

- `ratio_mae <= valid_ratio_mae_max`
- `efficiency >= valid_efficiency_min`
- `score >= valid_score_min`

`reference better_than_baseline=True` 需要同时满足：

- `reference_score >= baseline_score + better_score_margin`
- `reference_shape_cosine >= baseline_shape_cosine + better_shape_margin`

## 评测输出文件说明（artifacts）

`verification/evaluate.py` 会写入 `verification/artifacts/`：

- `summary.json`
  - 机器可读总结果，
  - 包含 spec、耗时、各项指标、总分、valid 与对比结论。
- `intensity_maps.png`
  - 目标图 / baseline 输出 / reference 输出并排图，
  - 用于快速看“位置对不对、形状像不像”。
- `ratios_and_losses.png`
  - 焦点功率比例柱状图（目标 vs baseline vs reference），
  - 训练 loss 曲线。

## 运行方式

```bash
PY=python3
$PY benchmarks/Optics/holographic_multifocus_power_ratio/verification/evaluate.py --device cpu
```

可选参数：

- `--seed`
- `--baseline-steps`
- `--reference-steps`
- `--artifacts-dir`

