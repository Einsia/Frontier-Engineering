# FT10 邻域移动选择任务

## 问题

你会拿到经典 FT10 作业车间实例，以及一个冻结好的局部搜索壳层。
你的任务是给相邻交换动作排序，让搜索过程更快找到更小的 makespan。

这不是“从头构造完整排程”的题。
评测器已经知道如何生成初始排程、构造邻域、执行 swap，并在合适的时候停止搜索。
你只需要提供一个动作评分策略。

## 背景

作业车间调度是制造业里非常经典的优化问题：
每个 job 必须按固定顺序经过若干机器，而每台机器同一时刻只能处理一个操作。
目标通常是最小化最后完成时间，也就是 makespan。

FT10 是一个经典的 10 job、10 machine 基准。
它之所以难，是因为局部看起来合理的机器顺序变化，可能会在全局上引入更长的关键路径，导致最终 makespan 变差。

这个教学任务的核心思想，是把“求解器壳层”和“策略”拆开。
你可以把它理解为：在一个组合优化 local search 引擎里学习一个排序函数。

## 哪些部分是冻结的

- FT10 实例 `ft10`
- 作为初始解的 incumbent 排程
- 相邻交换邻域
- 接受规则：只有改进的动作才会被应用
- 已知理论最优值 `930`

## 输入与输出

你的候选文件需要定义：

```python
def score_move(move, state):
    ...

MAX_ITERATIONS = 50
```

`score_move(move, state)` 的输入包含：

- `move`：描述一次相邻交换的字典
- `state`：描述当前局部搜索状态的字典

`move` 字典包含：

- `machine_id`：被修改的机器编号
- `machine_position`：相邻 pair 左边元素的位置
- `op_a` 和 `op_b`：这两个相邻操作
- `delta_duration`：由两个操作时长派生出的快速特征
- `current_makespan`：当前排程的 makespan

每个 `op_a` / `op_b` 里的操作记录都包含：

- `job_id`
- `op_index`
- `duration`
- `start`
- `end`

`state` 字典包含：

- `iteration`
- `current_makespan`

你只需要返回任意有限标量分数。
分数越大，动作越先被尝试。
如果你提供 `MAX_ITERATIONS`，它必须是正整数。

## 预期结果

一个好的提交应该返回可行排程，并让 makespan 比 baseline 更小。
这个实例的已知最优 makespan 是 `930`。

评测器大致会按下面的方式运行局部搜索：

1. 从 baseline incumbent 排程开始
2. 生成所有相邻机器顺序交换动作
3. 使用 `score_move(move, state)` 排序
4. 按排序结果应用第一个能改进的动作
5. 当没有改进动作，或者达到迭代上限时停止

所以，一个好的评分函数不只是“优先短操作”。
它还应该更偏向那些可能打开更好下游排程、缩短关键路径的 swap。

## 如何开始实现

如果你有 CS 背景，可以按下面这个很实用的思路入手：

1. 先把 `start` 和 `end` 当成 slack 的近似信号。
   越靠近排程尾部的操作，交换后越可能影响最终 makespan。
2. 通过操作在 job 里的位置，间接估计剩余工作量。
   如果一个 job 后面还有很多工序，过早把它卡住，代价通常更大。
3. 关注机器瓶颈。
   一台机器尾部附近的 swap，即使两个操作时长接近，也可能改变全局最慢链路。
4. 用“关键路径”来理解分数设计。
   makespan 由一条或几条没有松弛的紧约束链决定，真正有价值的 swap 往往是在缩短或重排这些链。

写代码时，通常不要只盯着 `delta_duration`，而是把几个弱信号组合成一个总分。

## 计分方式

这是一个最小化任务，所以 makespan 越小越好。
我们使用 0 到 100 的归一化分数：

```text
normalized_score = 100 * clip((baseline_makespan - candidate_makespan) / (baseline_makespan - 930), 0, 1)
```

含义是：

- `0` 表示候选解不比 baseline 更好
- `100` 表示候选解达到已知最优值 `930`
- 无效或不可行提交得分为 `0`

我们还会报告：

- `candidate_makespan`
- `baseline_makespan`
- `reference_makespan`
- `theoretical_optimum_makespan`
- `gap_to_optimum`

## 为什么难

最直觉的贪心想法是把短操作尽量往前排。
这有时有用，但它忽略了两个事实：机器冲突会约束顺序，job 前后依赖也会约束顺序。

真正难的是，一个局部 swap 会以非局部的方式改变关键路径。
你是在用局部邻域信号去改善一个全局目标，这正是这个 benchmark 想教你的地方。

## 判为无效的情况

如果出现以下任一情况，提交无效：

- 缺少 `score_move`
- 返回的分数不是有限值
- `MAX_ITERATIONS` 不合法
- 诱导出的排程不完整或不可行
- 评测器无法导入或运行候选文件

<!-- AI_GENERATED -->
