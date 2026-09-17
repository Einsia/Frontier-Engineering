# FT10 派工规则优化

## 任务概览

为经典 FT10 Fisher-Thompson 10x10 作业车间设计贪心派工规则，并尽量缩短 makespan。

这个 benchmark 对应的是车间在线派工场景。现实里，轻量级优先级规则依然很常用，因为它们易于部署，而且真的会影响吞吐、延误和加班。

你并不是直接输出完整排程，而是在一个冻结调度器内部写优先级函数，所以这道题本质上是在固定模拟器里的策略设计。

## 哪些部分是冻结的

- 经典 `ft10` 实例，以及已知最优值 `930`。
- `runtime/problem.py` 中冻结的调度构造器、可行性逻辑和 tie-breaking 协议。
- 只有最早可开工的操作才会交给你的评分函数比较的这条规则。

## 提交接口

提交一个 Python 文件，定义：

```python
def score_operation(operation, state):
    ...
```

返回任意有限标量优先级。在最早可开工时间相同的候选操作里，分数更高的会被优先调度。

## 评测流程

1. 从 `runtime/problem.py` 载入经典 `ft10` 实例。
2. 从空排程开始，反复收集每个 job 的下一个未调度操作。
3. 在最早可开工时间相同的操作中，选择 `score_operation(...)` 最高的那个。
4. 构造完整排程，计算候选 makespan，并同时报告 baseline 与相对最优差距。

## 指标

- `combined_score`：`-candidate_makespan`
- `valid`：只有生成完整可行排程时才为 `1.0`
- `candidate_makespan`
- `baseline_makespan`
- `relative_gap_to_optimum`

## 判为无效的情况

- 缺少 `score_operation(...)`，或函数在评测中报错
- 返回的优先级不是有限值
- 诱导出的排程不可行，或没有排完整
- 在得到有效 makespan 之前评测就失败

<!-- AI_GENERATED -->
