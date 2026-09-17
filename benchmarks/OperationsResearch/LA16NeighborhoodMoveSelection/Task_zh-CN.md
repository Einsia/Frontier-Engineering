# LA16 邻域移动选择

## 任务概览

为经典 LA16 作业车间上的冻结局部搜索壳层排序相邻交换动作，并尽量缩短 makespan。

这个 benchmark 对应的是 LA16 上有限搜索预算下的排程改进。搜索壳层本身是冻结的，只有你的动作排序策略能改变搜索轨迹。

你调的是一个固定组合优化器里的启发式控制策略，而不是从头输出一张排程。

## 哪些部分是冻结的

- 经典 `la16` 实例，以及已知最优值 `945`。
- 作为初始 incumbent 的 baseline SPT 派工排程。
- `runtime/problem.py` 中冻结的相邻交换邻域生成器和 first-improving 接受规则。

## 提交接口

提交一个 Python 文件，定义：

```python
MAX_ITERATIONS = 50


def score_move(move, state):
    ...
```

定义 `score_move(move, state)` 并返回任意有限标量；分数更高的动作会被优先尝试。你也可以把 `MAX_ITERATIONS` 设成任意正整数，以调整搜索预算。

## 评测流程

1. 从 `runtime/problem.py` 载入经典 `la16` 实例。
2. 从冻结的 baseline 派工排程开始。
3. 反复生成相邻机器顺序交换动作，按 `score_move(...)` 排序，并应用第一个能改进的动作。
4. 当不存在改进动作或达到 `MAX_ITERATIONS` 时停止，并输出候选 makespan 与诊断指标。

## 指标

- `combined_score`：`-candidate_makespan`
- `valid`：只有生成完整可行排程时才为 `1.0`
- `candidate_makespan`
- `baseline_makespan`
- `relative_gap_to_optimum`

## 判为无效的情况

- 缺少 `score_move(...)`，或函数在评测中报错
- 返回的动作分数不是有限值
- `MAX_ITERATIONS` 不合法，或在得到有效排程之前评测就失败
- 诱导出的排程变得不可行

<!-- AI_GENERATED -->
