# 任务：复合材料层合板铺层优化

## 1. 工程问题

设计一个 48 层正交各向异性复合材料板的铺层顺序。铺层需要在多种几何尺寸和载荷
比例下同时抵抗材料失效和板屈曲。这是一个耦合的离散结构设计问题：把高刚度方向
的铺层放到外侧可能提高屈曲性能，但改变纤维方向也会改变面内强度，并可能损害另一
载荷工况。

本任务源自采用 MIT 许可证发布的 Zenodo 数据集 *Beyond Double-Double Theory:
n-Directional Stacking Sequence Optimisation in Composite Laminates*
（[doi:10.5281/zenodo.15864525](https://doi.org/10.5281/zenodo.15864525)）。任务保留了
原发布代码中的 48 层构造、正交各向异性材料、单层厚度、五种长宽比、单轴/双轴压缩、
应变许用值和 Haftka 参考铺层。评测器采用独立的 NumPy 实现，详见
`references/design_notes.md`。

## 2. 候选程序接口

在 `scripts/init.py` 中实现：

```python
def design_laminates(cases: list[dict]) -> dict[str, list[int]]:
    ...
```

函数一次收到所有公开工况。每个工况仅包含 `case_id`、长宽比、板长宽和 `Nx/Ny`
膜内载荷。负值表示压缩；`Ny_N_per_mm == 0` 表示单轴载荷。

返回字典必须恰好包含输入给出的全部 `case_id`。每个值必须是可 JSON 序列化的列表，
包含恰好 12 个 `[0, 90]` 闭区间内的有限整数角度。

## 3. 铺层构造

对于候选角度 `theta_1 ... theta_12`，评测器先构造：

```text
[theta_1, -theta_1, theta_2, -theta_2, ..., theta_12, -theta_12]
```

再追加其逆序，得到平衡、对称的 48 层铺层。候选程序需要优化角度选择和厚度方向顺序，
但不需要自行修复制造约束。

## 4. 评测工况与物理模型

十个确定性工况由长宽比 `0.5, 1, 2, 3, 4` 与单轴、双轴压缩组合而成。板宽固定为
`127 mm`，长度随长宽比变化。材料、载荷和许用值记录在 `references/config.json`。

评测器使用经典层合板理论计算 `A`、`B`、`D`，然后求得：

1. 由最危险的纵向、横向或剪切层内应变确定的最大应变失效载荷因子；
2. 通过双正弦 Ritz 基、数值积分和对称广义特征值问题得到的简支板屈曲载荷因子。

控制储备因子为：

```text
reserve = min(failure_load_factor, buckling_load_factor)
```

## 5. 评分

每个工况相对于已发布的 Haftka 参考铺层归一化：

```text
case_score = clip(50 + 50*tanh(log(reserve/anchor_reserve)/0.5), 0, 100)
```

最终诊断分数为 `75%` 平均工况分加 `25%` 的第 20 百分位工况分。缺少工况、多余 ID、
错误类型、非整数或越界角度、超时、导入失败或非法力学结果都会令 `combined_score=0`；
逐工况诊断反馈仍会保留。

## 6. 运行与完整性约束

- `design_laminates` 必须确定性、可独立运行。
- 候选程序在受时间限制的独立 Python 进程中导入和执行。
- 工况和设计通过 JSON-lines 协议交换；候选 stdout 会被丢弃。
- 这是进程隔离，并非操作系统安全沙箱。
- 不得读取或修改 evaluator、参考参数、输出或环境机密文件。
- 仅修改 `scripts/init.py` 内 `EVOLVE-BLOCK` 标记之间的区域。

## 7. 运行命令

```bash
python verification/evaluator.py scripts/init.py
python -m frontier_eval task=unified \
  task.benchmark=StructuralOptimization/CompositeLaminateStacking \
  algorithm=openevolve algorithm.iterations=0
```
