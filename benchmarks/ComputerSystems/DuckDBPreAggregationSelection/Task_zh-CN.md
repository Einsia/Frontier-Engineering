# DuckDB 预聚合选择

## 任务概览

在冻结的 DuckDB 报表 workload 上，从白名单中选择一组预聚合表，尽量降低总执行时间。

这个 benchmark 对应的是数据仓库里很常见的一类决策：面对重复报表 workload，到底哪些汇总表值得物化。选错了会浪费存储和刷新成本，选对了才能真正降低重复扫描与聚合开销。

从算法角度看，它是固定候选集合上的物化视图选择题，而且分数来自真实查询执行，同时要满足严格结果一致性。

## 哪些部分是冻结的

- `runtime/problem.py` 中冻结的 schema、本地数据生成逻辑和报表 workload。
- `workload_manifest["candidate_preaggregations"]` 中给出的合法预聚合白名单。
- 固定的正确性校验与计时协议，统计建表开销和重复报表执行开销。

## 提交接口

提交一个 Python 文件，定义：

```python
def select_preaggregations(workload_manifest):
    ...
```

返回白名单中的预聚合名列表；也接受带 `preaggregations` 字段的字典。

## 评测流程

1. 构建冻结的 DuckDB 数据库并加载 workload manifest。
2. 创建你从白名单中选出的预聚合表。
3. 执行固定报表查询并校验结果是否一致。
4. 统计候选总耗时，并同时给出不物化任何汇总表的 baseline。

## 指标

- `combined_score`：`-candidate_total_runtime_s`
- `valid`：只有名字合法且查询结果不变时才为 `1.0`
- `candidate_total_runtime_s`
- `baseline_total_runtime_s`
- `candidate_setup_runtime_s`
- `candidate_workload_runtime_s`

## 判为无效的情况

- 缺少 `select_preaggregations(...)`，或函数在评测中报错
- 返回值无法解析为预聚合名列表
- 任意一个名字不在白名单中
- 物化失败、查询执行失败，或结果发生变化

<!-- AI_GENERATED -->
