# 题目 03：跨目标鲁棒优化（QAOA）

## 目标
优化 QAOA 电路，使同一策略在两个目标上都有效：
- `ibm_falcon_27`
- `ionq_aria_25`

每个 case 都会在两个目标上评测，降低单设备过拟合。

## 可修改范围
- 只允许修改 `baseline/solve.py`。

## 评测流程
对每个 case，评测器会：
1. 使用 case 中 `seed` 和 `repetitions` 在 `BenchmarkLevel.ALG` 生成 QAOA 输入。
2. 对 `case["targets"]` 中每个目标调用 `optimize_circuit(input_circuit, target, case)`。
3. 分目标对 candidate 做一次规范化（`optimization_level=0`）后评分。
4. 分目标生成 mapped-level `opt_level=0..3` 参考电路。
5. 对每个 `(case, target)` 输出 candidate 与各 opt-level 对比，并计算归一化分数。

## 输入 / 输出接口
`baseline/solve.py` 必须提供：

```python
def optimize_circuit(input_circuit, target, case):
    ...
    return optimized_circuit
```

输入：
- `input_circuit`：按测例配置生成的 Qiskit `QuantumCircuit`。
- `target`：当前目标硬件对应的 Qiskit `Target`。
- `case`：来自 `tests/case_*.json` 的字典；评测时会追加 `target_name` 字段。

输出：
- `optimized_circuit`：Qiskit `QuantumCircuit`。

## 正确性门禁（在计算任何指标之前执行）

评测器会在统计深度与门数**之前**，先校验你的电路与输入电路是否功能等价。
未通过的电路不会被打分：整次运行判为 invalid，而不是给一个低分。

- 方法：态矢抽样。用 `|0...0>` 加 4 个 Haar 随机输入态分别通过两个电路演化并比对，
  逐态保真度的最小值必须大于 `1 - 1e-9`。
- 忽略全局相位；也允许路由引入的比特置换——前提是你的电路声明了它（见下）。
- 会被拒绝：空电路、未达到保真度阈值的电路、`reset`、中途测量、经典条件门，
  以及作用比特数超过 22 的电路。

## 比特布局（layout）

ALG 层的 QAOA 电路不含测量，评测器无法从电路本身还原路由置换。若你返回的电路比
输入更宽，它必须携带 transpiler 的 layout。直接返回 `transpile()` 的结果即可；
若要再做后处理，请保留 `circuit._layout`
（`baseline/structural_optimizer.py` 已经这样做了）。与输入等宽且无 layout 的电路
按恒等映射处理。声明的 layout 只是提示而非权威：声明了却没有真正实现的置换一样
过不了校验。

## 执行模型

`baseline/solve.py` 在独立解释器中运行。输入电路以 OpenQASM 3 传入，你返回的电路
也会被导出为 OpenQASM 3，并由评测器重新解析和计算指标。

## 成本函数与归一化分数
成本函数：
- `cost = two_qubit_count + 0.2 * depth`

归一化分数：
- `score_0_to_3 = 3 * (opt0_cost - x_cost) / (opt0_cost - opt3_cost)`

含义：
- `opt=0` 参考分数恒为 `0`。
- `opt=3` 参考分数恒为 `3`。
- candidate 在同一标尺上按目标分别打分。

## 测例
每个测例都会在两个目标（`ibm_falcon_27`、`ionq_aria_25`）上展开：
- `cross_target_case_01`（`tests/case_01.json`）：`benchmark=qaoa`，`num_qubits=10`，`repetitions=2`，`seed=11`
- `cross_target_case_02`（`tests/case_02.json`）：`benchmark=qaoa`，`num_qubits=12`，`repetitions=2`，`seed=17`
- `cross_target_case_03`（`tests/case_03.json`）：`benchmark=qaoa`，`num_qubits=14`，`repetitions=3`，`seed=31`

共 6 个 `(case, target)` 评测组合。

## 当前基线（`baseline/solve.py`）
规则重写实现，不直接调用 `transpile`：
1. 去掉 barrier
2. 消去相邻逆门/自反门
3. 合并相邻参数旋转门

## 评测产物保存
每次评测默认保存到 `runs/eval_<timestamp>/`。

每个 `(case, target)` 目录包含：
- `input.qasm` + `input.png`
- `candidate_raw.qasm` + `candidate_raw.png`
- `candidate_canonical.qasm`
- `reference_opt_0.qasm`
- `reference_opt_1.qasm`
- `reference_opt_2.qasm`
- `reference_opt_3.qasm`
