# DuckDB 查询重写

## 任务概览

重写一条冻结的 DuckDB 分析 SQL，在保证结果完全一致的前提下尽量缩短运行时间。

这个 benchmark 对应的是真实 SQL 调优场景：工程师往往不能改上游产品逻辑，但仍然可以通过重写一条慢查询来提速。这里性能当然重要，但前提永远是语义必须完全不变。

从计算机视角看，这是一道保持语义不变的程序变换题，只不过这里被优化的“程序”是 SQL。

## 哪些部分是冻结的

- `runtime/problem.py` 中冻结的 schema、本地数据生成逻辑、原始 SQL 和 workload manifest。
- 评测器使用的精确结果等价性校验。
- 用于比较候选查询与 baseline 查询的固定重复计时协议。

## 提交接口

提交一个 Python 文件，定义：

```python
def rewrite_query(sql, workload_manifest):
    ...
```

返回重写后的 SQL 字符串；也接受带 `sql` 字段的字典。

## 评测流程

1. 构建冻结的 DuckDB 数据库，并先执行原始 SQL 得到参考结果。
2. 执行你重写后的 SQL，并做精确结果等价校验。
3. 只有结果一致时，才会继续对候选查询做重复计时。
4. 输出候选运行时间，并同时给出原始查询的 baseline。

## 指标

- `combined_score`：`-candidate_runtime_s`
- `valid`：只有重写后的查询精确保留结果时才为 `1.0`
- `candidate_runtime_s`
- `baseline_runtime_s`
- `row_count`

## 判为无效的情况

- 缺少 `rewrite_query(...)`，或函数在评测中报错
- 返回值不是 SQL 字符串，也不是带 `sql` 字段的字典
- 重写后的查询无法执行
- 重写后的查询改变了结果集

<!-- AI_GENERATED -->
