# 自适应光学 A3 说明：能耗感知控制

## 领域背景

这是一个**多目标优化**任务。

AO 控制如果只最小化残差，通常会输出幅值大、通道密集的命令向量。在工程系统中，这直接关联：

- 执行器功耗与热负载，
- 长期可靠性，
- 驱动电路余量。

因此要同时兼顾补偿质量和命令能耗。

## 你需要做什么

只修改一个函数：

- 文件：`baseline/init.py`
- 目标函数：

```python
def compute_dm_commands(slopes, reconstructor, control_model, prev_commands=None, max_voltage=0.35):
    ...
```

目标：
- 提高 `score_0_to_1_higher_is_better`。
- 每次调用都满足 valid 约束。



### 输入

- `slopes: np.ndarray`，形状 `(2 * n_subap,)`
  - 当前帧（延迟/噪声后）斜率向量。
- `reconstructor: np.ndarray`，形状 `(n_act, 2 * n_subap)`
  - baseline 线性映射。
- `control_model: dict`
  - 稀疏控制参数与动态补偿参数：
    - `h_matrix`
    - `lasso_alpha`, `lasso_max_iter`, `lasso_tol`
    - `delay_comp_gain`
    - `temporal_blend`
- `prev_commands: np.ndarray | None`，形状 `(n_act,)`
  - 上一帧命令（可选）。
- `max_voltage: float`
  - 每通道电压上限。

### 输出

- `dm_commands: np.ndarray`，形状 `(n_act,)`
  - 必须形状正确、数值有限、且不越界。

## 执行契约（候选在独立进程中运行）

`verification/evaluate.py` 不再把 `baseline/init.py` import 进评分进程，而是把它
作为独立脚本在临时目录中启动，因此候选无法观察或干预评分过程。

评测器放进该目录的输入（`problem.npz`，用
`np.load("problem.npz", allow_pickle=False)` 读取）：

- `slopes`：`(n_cases, 2 * n_subap)`，完整 WFS 斜率流，每行一帧
- `reconstructor`：`(n_act, 2 * n_subap)`
- `cm__*`：`control_model` 的各项（去掉 `cm__` 前缀即可还原字典）
- `max_voltage`、`n_act`、`actuator_lag`

候选退出前必须在工作目录写出：

- `submission.npz`，含唯一浮点数组 `commands`，形状 `(n_cases, n_act)`
  - 第 `i` 行是控制器针对第 `i` 个观测发出的命令
  - 所有元素必须有限，且落在 `[-max_voltage, max_voltage]` 内

`baseline/init.py` 底部的 `if __name__ == "__main__":` 运行器已经实现了这套流程：
遍历观测流、调用你的函数、按文档中的执行器滞后递推重建 `prev_commands`
（`applied = lag * applied + (1 - lag) * cmd`），并保存结果。**请保留它。**
崩溃、超时或没有产出合法 `submission.npz` 的运行一律判为无效
（`combined_score = -1e18`），而不是只扣分。

评测器只根据 `commands` 重新计算一切——它自己重跑执行器滞后，再算
残差、RMS 与 Strehl。写进 `submission.npz` 的任何 score/cost/metric 字段都会被忽略。

## Verification 场景

`verification/evaluate.py` 构造动态且含失配的评测环境：

1. 时间相关的模态相位演化。
2. 延迟+噪声的 WFS 观测。
3. 执行器一阶滞后。
4. 真实系统增益与名义模型不一致。

在这个场景里，仅追求残差最小往往不如能耗感知策略。

## 指标与分数（0~1，越高越好）

排行榜字段：
- `score_0_to_1_higher_is_better`，范围 `[0, 1]`
- `score_percent = 100 * score_0_to_1_higher_is_better`

原始指标：
- `mean_rms`（越低越好）
- `mean_abs_command`（越低越好）
- `mean_sparsity`（越高越好，近零比例）
- `mean_strehl`（越高越好）

utility 加权分数：
- `0.15 * U(mean_rms)`
- `0.60 * U(mean_abs_command)`
- `0.15 * U(mean_sparsity)`
- `0.10 * U(mean_strehl)`

锚点：
- 越低越好：
  - `mean_rms`: good `1.55`, bad `2.25`
  - `mean_abs_command`: good `0.08`, bad `0.36`
- 越高越好：
  - `mean_sparsity`: good `0.40`, bad `0.00`
  - `mean_strehl`: good `0.22`, bad `0.08`

`raw_cost_lower_is_better` 仅用于诊断，不是排行榜方向。

## Baseline 实现

当前 baseline（`baseline/init.py`）：
1. `u = reconstructor @ slopes`
2. `clip` 到边界

弱点：
- 没有显式能耗正则
- 容易输出高幅值、低稀疏命令

## Oracle / Reference 实现

reference（`verification/reference_controller.py`）使用第三方 `scikit-learn` Lasso：

- 求解器：`sklearn.linear_model.Lasso`
- 目标形式：
  - `(1/(2m)) * ||H u - s||^2 + alpha * ||u||_1`
- 可选延迟补偿（利用 `prev_commands`）
- 时间融合增强稳定性
- 最后 clip 保证盒约束

它是强基准，因为：
- 使用标准稀疏优化后端
- 能自然降低命令能耗并提升稀疏性

## verification/outputs 文件作用

运行：

```bash
python verification/evaluate.py
```

会生成：

- `metrics.json`
  - baseline/reference 结构化结果（分数、原始指标、评测配置）。
  - 自动化评测和回归对比的核心输入。
- `metrics_comparison.png`
  - 关键指标与分数的柱状图对比。
- `example_visualization.png`
  - 代表样本的 phase/residual/PSF 可视化。
  - 用于直观看到质量-能耗折中的效果。

## 依赖与约束策略

- Baseline 期望轻量（`numpy` + 给定矩阵）。
- Reference 允许使用第三方 `scikit-learn`。
- 不接受通过线程参数刷分。
