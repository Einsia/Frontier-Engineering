# 多机器人优先级路径规划

## 任务概览

在冻结的栅格地图上为 3 台机器人规划无碰撞路径，并尽量降低总路径代价。

这个 benchmark 对应的是共享巷道里的小规模机器人协同规划。好的路径集合既要避免互相阻塞和死锁，也不能把总路程拉得太长。

从计算角度看，它是一个小规模 multi-agent path finding 问题。单机器人最短路不难，真正的难点是让多条路径同时避开顶点冲突和边交换冲突。

## 哪些部分是冻结的

- `runtime/problem.py` 中冻结的占据栅格、3 组起终点以及冲突检查器。
- 固定规则：每台机器人每一步可以移动到相邻格点，也可以原地等待，但全体路径必须同时避开顶点冲突和边交换冲突。
- 用于对照的 baseline prioritized planner，以及各机器人独立最短路的下界。

## 提交接口

提交一个 Python 文件，定义：

```python
def plan_paths(grid, starts, goals):
    ...
```

返回一个路径列表，每台机器人对应一条；也接受带 `paths` 字段的字典。

## 评测流程

1. 从 `runtime/problem.py` 载入冻结的栅格、起点和终点。
2. 逐条检查机器人路径，包括起终点、相邻/等待移动规则和障碍检查。
3. 再按时间维度联合检查顶点冲突和边交换冲突。
4. 输出总路径代价、makespan、baseline 总代价和理论下界诊断。

## 指标

- `combined_score`：`-candidate_total_cost`
- `valid`：只有所有机器人路径都无冲突时才为 `1.0`
- `candidate_total_cost`
- `baseline_total_cost`
- `candidate_makespan`
- `lower_bound_total_cost`

## 判为无效的情况

- 缺少 `plan_paths(...)`，或函数在评测中报错
- 返回值无法解析为每台机器人各一条路径
- 任意机器人路径起终点错误、包含非法移动，或进入障碍物
- 联合路径集合中出现顶点冲突或边交换冲突

<!-- AI_GENERATED -->
