# 题目 04：量子纠错解码器（旋转表面码）

## 目标

实现容错量子计算机控制回路中实际要运行的那个经典解码器：给定一个 graphlike detector
error model 和一批从旋转表面码 memory 实验采样得到的 syndrome 比特串，预测逻辑观测量的
翻转。

解码器质量直接决定逻辑错误率，从而决定任何有用算法所需的物理比特开销。最小权完美匹配
（MWPM）二十年来一直是社区参考解码器，但它并非最优：它把错误模型拆成一张图，因而丢掉了
电路级去极化噪声真实产生的 X/Z 关联。关联匹配、带 ordered-statistics 后处理的置信传播、
张量网络解码器、学习型解码器都报告过更低的逻辑错误率。**超越 MWPM 是当前的研究前沿，
因此分数不设上限：追平 MWPM 得 1.0，超过它得大于 1.0。**

## 可修改范围

- 只允许修改 `baseline/solution.py`。

## 输入 / 输出接口

`baseline/solution.py` 必须提供：

```python
def decode(problem, detection_events):
    """Predict logical observable flips from syndrome data."""
```

`problem` 描述一次 memory 实验：

- `num_detectors`、`num_observables`、`distance`、`rounds`；
- `errors`：**graphlike detector error model**，一个由相互独立的错误机制组成的列表。
  每一项形如 `{"p": float, "dets": [int, ...], "obs": [int, ...]}`，其中 `p` 是该机制
  独立触发的概率，`dets` 是它翻转的检测器集合（最多两个，因为模型已被分解），`obs`
  是它翻转的逻辑观测量集合。

`detection_events` 是形状为 `(shots, num_detectors)` 的布尔数组：每一发（shot）哪些检测器
被触发。检测器是相邻轮次稳定子测量之间的奇偶校验，因此一次物理故障通常点亮两个检测器——
即一条错误链的两个端点。

返回形状为 `(shots, num_observables)`、取值为 0/1 的数组：每一发中，你认为每个逻辑观测
量是否被翻转。元素可以是 `bool`、整数，或严格等于 `0.0`/`1.0` 的浮点数。

真实的观测量翻转永远不会告诉你。唯一的证据是错误模型与 syndrome。

## 评测流程

对每个 regime，评测器会：

1. 用 Stim 按该 regime 的 `(distance, noise)` 生成旋转表面码 memory 线路。
2. 用固定随机种子采样 `shots` 份 syndrome，并把真实观测量翻转单独留存。
3. 在同一个分解错误模型、同一批 shot 上重算 MWPM 参考（PyMatching 2），使 anchor 不会
   与被打分的样本脱节。
4. 只在独立解释器中把错误模型与 syndrome 交给你的解码器。
5. 将你的预测与真实翻转比对并打分。

## 成本函数与分数

对每个 regime，设逻辑错误率为 `L`：

```text
score = ( log L_trivial - log L_candidate ) / ( log L_trivial - log L_mwpm )
```

- `L_trivial` 是"永不预测翻转"的解码器的错误率。得 0 分意味着你不比无视 syndrome 更好；
  引入额外逻辑错误的解码器被截断在 0。
- `L_mwpm` 是同一分解错误模型上的最小权完美匹配。追平它得 1.0。
- **上限不封顶**：真正优于匹配的解码器可以得到大于 1.0 的分数。

`combined_score` 是四个 development regime 的平均值（搜索所优化的目标）。另外两个噪声强度
不在 development 集合中的 regime 单独计分并报告为 `robustness_score`，它们不进入
`combined_score`，也不会回传给搜索状态。

若任一 development regime 无效（形状错误、非二值元素、抛出异常、导入被禁模块，或超时），
则报告 `combined_score = 0.0` 与 `valid = 0.0`，并把逐 regime 的原因保留在 `artifacts.json`。

## Regimes

默认难度（`verification/evaluate.py` 中的 `DIFFICULTY = 1`）：

| Regime | distance | noise | shots | 检测器数 |
|---|---:|---:|---:|---:|
| `d3_p0.005` | 3 | 0.005 | 6000 | 24 |
| `d5_p0.005` | 5 | 0.005 | 6000 | 120 |
| `d5_p0.010` | 5 | 0.010 | 6000 | 120 |
| `d7_p0.005` | 7 | 0.005 | 6000 | 336 |

Sealed regime（报告为 `robustness_score`）：

| Regime | distance | noise | shots | 检测器数 |
|---|---:|---:|---:|---:|
| `sealed_d5_p0.007` | 5 | 0.007 | 4000 | 120 |
| `sealed_d7_p0.008` | 7 | 0.008 | 4000 | 336 |

不要把上述数值写死：每个 regime 都会给出自己的 `distance`、`rounds`、`num_detectors`、
`num_observables` 与分解后的 `errors`，shot 数就是 `detection_events` 的第一个维度。从
problem 里读取几何信息的解码器在任何难度下都能工作；假定 `d=3` 的不能。

## 解码时间预算

默认难度下，每个 development regime 给你 6000 发、每个 sealed regime 4000 发，候选子进程
必须落在 `QEC_CANDIDATE_TIMEOUT_S`（默认 240 s）之内，而整个 harness 预算为 300 s。

逐 shot 的 Python 循环重算最短路是跑不完的。只依赖错误模型的部分应当每个 regime 只预计算
一次，并尽量在 shot 维度上向量化。**正确但超时的解码器得 0 分。**

## 约束

1. 确定性 CPU 代码，仅使用 Python 标准库 + NumPy + SciPy。
2. 导入 `stim` 或 `pymatching` 属于无效提交：参考解码器是 anchor，不是答案。你的解码器
   运行期间评测器会拒绝这两个导入，并拒绝已绑定它们的模块。
3. syndrome 批次是唯一证据，真实翻转不会交给你的进程。
4. 不要读取 `verification/` 或 `frontier_eval/`。

## 复现

```bash
python verification/evaluate.py --candidate baseline/solution.py
```

框架兼容性验证：

```bash
python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_04_quantum_error_decoder \
  task.runtime.python_path=uv-env:frontier-v1-main algorithm=openevolve algorithm.iterations=0
```