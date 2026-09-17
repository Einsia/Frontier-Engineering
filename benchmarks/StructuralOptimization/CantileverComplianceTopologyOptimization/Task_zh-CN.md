# 悬臂梁柔顺度拓扑优化

## 任务概览

在冻结的悬臂梁 pyMOTO 拓扑优化循环中更新密度场，并尽量降低最终柔顺度。

这个 benchmark 对应的是轻量化支架和悬臂结构设计。在材料预算固定的前提下，目标就是让悬臂尽可能“更硬”。

从计算角度看，这更像是在冻结的 FEM/SIMP 循环里设计优化器，而不是一次性预测答案。

## 哪些部分是冻结的

- `runtime/problem.py` 中的 pyMOTO 有限元模型、几何、载荷、被动区域和 SIMP 设置。
- 材料体积分数预算、最小密度、单步 move limit，以及固定的 30 次迭代。
- 柔顺度目标和每一步密度更新的可行性校验逻辑。

## 提交接口

提交一个 Python 文件，定义：

```python
def update_density(density, sensitivity, state):
    ...
```

`density` 是当前密度向量，`sensitivity` 是当前柔顺度灵敏度，`state` 中包含 `iteration`、`domain_shape`、`volume_fraction`、`target_density_sum`、`minimum_density`、`move_limit`、`current_compliance`、`history`、`passive_solid_mask`、`passive_void_mask` 等字段。

返回下一步可行的密度向量；也接受带 `density` 字段的字典。如果需要投影辅助函数，可以从 `runtime.problem` 导入 `project_density`。

## 评测流程

1. 从 `runtime/problem.py` 构建冻结的 pyMOTO 模型。
2. 在固定的 30 次迭代优化循环里调用你的 `update_density(...)`。
3. 对每一步候选密度执行边界、move limit、被动区域和体积守恒校验。
4. 输出最终候选柔顺度，并同时给出 OC 风格基线作参考。

## 指标

- `combined_score`：`-candidate_compliance`
- `valid`：只有每一步更新都有限且可行时才为 `1.0`
- `candidate_compliance`
- `baseline_compliance`
- `final_volume_fraction`
- `volume_fraction_error`

## 判为无效的情况

- 缺少 `update_density(...)`，或函数在评测中报错
- 任意一步候选密度包含非有限值
- 任意一步更新违反边界、move limit、被动区域或目标体积约束
- 评测过程中 pyMOTO 求解失败

<!-- AI_GENERATED -->
