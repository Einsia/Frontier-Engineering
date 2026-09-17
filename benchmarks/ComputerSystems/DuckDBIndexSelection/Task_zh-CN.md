# DuckDB 索引选择

## 任务概览

在冻结的 DuckDB 分析 workload 上，从白名单中挑选一组索引，尽量降低总执行时间。

这个 benchmark 对应的是稳定 DuckDB workload 上的物理设计调优。额外索引确实可能加速重复查询，但也会带来构建和维护成本，所以关键不是“建得越多越好”，而是选对那一小部分。

从计算角度看，这是一道固定候选集合上的子集选择题，而且分数来自真实执行时间，不是某个替代指标。

## 哪些部分是冻结的

- `runtime/problem.py` 中冻结的 schema、本地数据生成逻辑和 workload manifest。
- `workload_manifest["candidate_indexes"]` 中给出的合法索引白名单。
- 固定的计时协议：先建索引，再重复执行 workload 四轮。

## 提交接口

提交一个 Python 文件，定义：

```python
def select_indexes(workload_manifest):
    ...
```

返回白名单中的索引名列表；也接受带 `indexes` 字段的字典。

## 评测流程

1. 构建冻结的 DuckDB 数据库并加载 manifest。
2. 创建你从白名单中选出的索引。
3. 固定重复执行查询 workload 四次。
4. 统计候选总耗时，并同时给出无索引 baseline 作为参考。

## 指标

- `combined_score`：`-candidate_total_runtime_s`
- `valid`：只有索引名合法且执行成功时才为 `1.0`
- `candidate_total_runtime_s`
- `baseline_total_runtime_s`
- `candidate_setup_runtime_s`
- `candidate_workload_runtime_s`

## 判为无效的情况

- 缺少 `select_indexes(...)`，或函数在评测中报错
- 返回值无法解析为索引名列表
- 任意一个索引名不在白名单中
- 建索引或执行 workload 时失败

<!-- AI_GENERATED -->
