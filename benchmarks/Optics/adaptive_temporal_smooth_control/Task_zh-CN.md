# 自适应光学 A2 说明：时间平滑控制


这是一个**时序控制问题**。

每一帧都要把传感器斜率 `s_t` 映射成 DM 命令 `u_t`。如果只追求单帧误差最小，常见后果是命令抖动很大。在真实硬件中会导致：

- 执行器磨损，
- 机械振动风险，
- 闭环稳定裕量下降。

所以目标不是“每帧最优”，而是“精度 + 平滑性”的工程折中。

## 你需要做什么

只修改一个函数：

- 可编辑文件：`baseline/init.py`
- 目标函数：

```python
def compute_dm_commands(slopes, reconstructor, control_model, prev_commands, max_voltage=0.25):
    ...
```

目标：
- 提升 `score_0_to_1_higher_is_better`。
- 保持输出始终 valid。



### 输入

- `slopes: np.ndarray`，形状 `(2 * n_subap,)`
  - 当前帧（延迟/噪声后）的 WFS 斜率。
- `reconstructor: np.ndarray`，形状 `(n_act, 2 * n_subap)`
  - baseline 线性映射。
- `control_model: dict`
  - 预计算控制矩阵和增益：
    - `smooth_reconstructor`
    - `prev_blend`
    - `reconstructor`
    - `delay_prediction_gain`
    - `command_lowpass`
- `prev_commands: np.ndarray`，形状 `(n_act,)`
  - 上一帧已执行命令（时序策略核心输入）。
- `max_voltage: float`
  - 电压边界。

### 输出

- `dm_commands: np.ndarray`，形状 `(n_act,)`
  - 必须有限且满足 `[-max_voltage, max_voltage]`。

## 执行契约（候选在独立进程中运行）

`verification/evaluate.py` 在独立子进程的临时工作目录中运行 `baseline/init.py`。

评测器放进该目录的输入（`problem.npz`，用
`np.load("problem.npz", allow_pickle=False)` 读取）：

- `slopes`：`(n_cases, 2 * n_subap)`，完整 WFS 斜率流，每行一帧
- `reconstructor`：`(n_act, 2 * n_subap)`
- `cm__*`：`control_model` 的各项（去掉 `cm__` 前缀即可还原字典）
- `max_voltage`、`n_act`、`actuator_lag`、`rate_limit`、`episode_length`、`n_episodes`
  - 数据流按 episode 排布：`[ep * episode_length : (ep + 1) * episode_length]`
    为一个 episode，每个 episode 从平面镜重新开始

候选退出前必须在工作目录写出：

- `submission.npz`，含唯一浮点数组 `commands`，形状 `(n_episodes * episode_length, n_act)`
  - 第 `i` 行是控制器针对第 `i` 个观测发出的命令
  - 所有元素必须有限，且落在 `[-max_voltage, max_voltage]` 内

`baseline/init.py` 底部的 `if __name__ == "__main__":` 运行器已经实现了这套流程：
遍历观测流、调用你的函数、按文档中的速率限幅 + 执行器滞后递推重建 `prev_commands`，
并在每个 episode 边界重置，并保存结果。**请保留它。**
崩溃、超时或没有产出合法 `submission.npz` 的运行一律判为无效
（`combined_score = -1e18`），而不是只扣分。

评测器只根据 `commands` 重新计算一切——它自己重跑速率限幅与执行器滞后，再算
残差、RMS 与 Strehl。写进 `submission.npz` 的任何 score/cost/metric 字段都会被忽略。

## Verification 场景

评测器模拟了较真实的时序 AO 环境：

1. 湍流模态按随机动力学演化。
2. 观测斜率存在延迟和噪声。
3. 执行器存在一阶滞后。
4. 施加执行器速率限制（`ACTUATOR_RATE_LIMIT`）。
5. 真实系统与名义模型有增益失配。

好的控制器需要在延迟观测下避免过度反应，并降低命令跳变。

## 指标与分数（0~1，越高越好）

排行榜目标：
- `score_0_to_1_higher_is_better`，范围 `[0, 1]`
- `score_percent = 100 * score_0_to_1_higher_is_better`

原始指标：
- `mean_rms`（越低越好）
- `mean_slew = mean(|u_t - u_{t-1}|)`（越低越好）
- `mean_strehl`（越高越好）

加权 utility 分数：
- `0.20 * U(mean_rms)`
- `0.65 * U(mean_slew)`
- `0.15 * U(mean_strehl)`

锚点：
- 越低越好：
  - `mean_rms`: good `1.45`, bad `2.10`
  - `mean_slew`: good `0.045`, bad `0.19`
- 越高越好：
  - `mean_strehl`: good `0.24`, bad `0.10`

`raw_cost_lower_is_better` 仅用于调试分析。

## Baseline 实现

当前 baseline（`baseline/init.py`）：
1. `u = reconstructor @ slopes`
2. `clip` 到电压边界

弱点：
- 不使用 `prev_commands`
- 不处理平滑目标
- 不补偿延迟观测

## Oracle / Reference 实现

reference（`verification/reference_controller.py`）为解析平滑控制器：

- 使用预计算矩阵形成平滑主项：
  - `u = smooth_reconstructor @ slopes + prev_blend @ prev_commands`
- 增加延迟前馈补偿：
  - 使用 `delay_prediction_gain`
- 可选与上一帧做低通融合：
  - `command_lowpass`
- 最后 clip 保证边界

它不依赖重型外部优化器，但明显强于逐帧独立控制。

## verification/outputs 文件作用

运行：

```bash
python verification/evaluate.py
```

会在 `verification/outputs/` 生成：

- `metrics.json`
  - baseline(candidate) 与 reference 的完整数值报告。
  - 包含分数、原始指标、配置参数、锚点和权重。
- `metrics_comparison.png`
  - 关键指标并排柱状图，快速判断差距。
- `example_visualization.png`
  - 代表样本的 phase/residual/PSF 可视化对比。
  - 用于确认分数提升是否对应更合理的物理补偿。

## 依赖与约束策略

- Baseline 期望保持轻量（`numpy` + 给定矩阵）。
- Reference 为解析形式，不依赖外部优化求解器。
- 不允许通过改线程数等方式刷分。
