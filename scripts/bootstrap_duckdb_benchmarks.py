#!/usr/bin/env python3

from __future__ import annotations

import textwrap
from pathlib import Path


TASKS = [
    {
        "slug": "DuckDBIndexSelection",
        "title": "DuckDB Index Selection",
        "short": "Choose a small set of DuckDB indexes for a frozen analytical lookup workload.",
        "kind": "index",
        "source_manifest": """\
# Source Manifest

- Upstream engine: `DuckDB`
- Upstream lineage:
  - DuckDB benchmark and TPC-H documentation
  - DuckDB SQL and index support
- Schema lineage: this benchmark uses a local frozen relational workload with `customer`, `orders`, and `lineitem` tables modeled after the TPC-H schema family.
- Data provenance: rows are generated deterministically inside DuckDB from fixed SQL formulas and a fixed schema; this is a benchmark-local synthetic dataset, not official TPC-H `dbgen` output.
- Authenticity note: the schema and workload lineage are traceable to official DuckDB/TPC-H benchmarking materials, but the data itself is a local frozen synthetic asset used because online extension-based generation was not reliable in this environment.
- License lineage: DuckDB is released under the MIT License.
""",
    },
    {
        "slug": "DuckDBQueryRewrite",
        "title": "DuckDB Query Rewrite",
        "short": "Rewrite a frozen DuckDB analytical SQL query to preserve results while reducing total runtime.",
        "kind": "rewrite",
        "source_manifest": """\
# Source Manifest

- Upstream engine: `DuckDB`
- Upstream lineage:
  - DuckDB benchmark and TPC-H documentation
  - DuckDB SQL optimizer and query execution model
- Schema lineage: this benchmark uses a local frozen relational workload with `customer`, `orders`, and `lineitem` tables modeled after the TPC-H schema family.
- Data provenance: rows are generated deterministically inside DuckDB from fixed SQL formulas and a fixed schema; this is a benchmark-local synthetic dataset, not official TPC-H `dbgen` output.
- Authenticity note: the workload shape is traceable to official DuckDB/TPC-H analytical reporting patterns, while the exact query instance is a benchmark-local frozen SQL task chosen to expose meaningful rewrite opportunities.
- License lineage: DuckDB is released under the MIT License.
""",
    },
    {
        "slug": "DuckDBPreAggregationSelection",
        "title": "DuckDB Pre-Aggregation Selection",
        "short": "Choose a small set of pre-aggregation tables for a frozen DuckDB reporting workload.",
        "kind": "preaggregation",
        "source_manifest": """\
# Source Manifest

- Upstream engine: `DuckDB`
- Upstream lineage:
  - DuckDB benchmark and TPC-H documentation
  - DuckDB SQL execution on analytical reporting queries
- Schema lineage: this benchmark uses a local frozen relational workload with `customer`, `orders`, and `lineitem` tables modeled after the TPC-H schema family.
- Data provenance: rows are generated deterministically inside DuckDB from fixed SQL formulas and a fixed schema; this is a benchmark-local synthetic dataset, not official TPC-H `dbgen` output.
- Authenticity note: the reporting queries and schema family are traceable to official analytical benchmark patterns, while the candidate pre-aggregations are benchmark-local frozen physical-design options.
- License lineage: DuckDB is released under the MIT License.
""",
    },
]


HELPER_TEXT = """\
from __future__ import annotations

import math
import time
from typing import Any

import duckdb


CUSTOMER_COUNT = 20_000
ORDER_COUNT = 120_000
LINEITEM_COUNT = 600_000

SEGMENTS = ("BUILDING", "AUTOMOBILE", "HOUSEHOLD", "FURNITURE", "MACHINERY")
SHIPMODES = ("AIR", "MAIL", "RAIL", "TRUCK", "SHIP")

CUSTOMER_KEYS = tuple(1 + ((i * 97) % CUSTOMER_COUNT) for i in range(1, 301))
ORDER_KEYS = tuple(1 + ((i * 193) % ORDER_COUNT) for i in range(1, 301))


INDEX_CANDIDATES = {
    "idx_orders_cust": "CREATE INDEX idx_orders_cust ON orders(o_custkey)",
    "idx_orders_date": "CREATE INDEX idx_orders_date ON orders(o_orderdate)",
    "idx_lineitem_order": "CREATE INDEX idx_lineitem_order ON lineitem(l_orderkey)",
    "idx_customer_segment": "CREATE INDEX idx_customer_segment ON customer(c_mktsegment)",
    "idx_orders_priority": "CREATE INDEX idx_orders_priority ON orders(o_orderpriority)",
}

INDEX_WORKLOAD_MANIFEST = {
    "schema_lineage": "TPC-H-inspired customer/orders/lineitem local workload",
    "candidate_indexes": tuple(sorted(INDEX_CANDIDATES)),
    "workload_notes": (
        "Repeated selective customer lookups on orders",
        "Repeated selective order lookups on lineitem",
        "Repeated priority-filtered joins from customer to orders",
    ),
    "repetitions": 4,
}


PREAGGREGATION_CANDIDATES = {
    "agg_quarter_segment_revenue": (
        "CREATE TABLE agg_quarter_segment_revenue AS "
        "SELECT date_trunc('quarter', o.o_orderdate) AS quarter_bucket, "
        "       c.c_mktsegment AS segment, "
        "       sum(l.l_extendedprice * (1 - l.l_discount)) AS revenue "
        "FROM customer c "
        "JOIN orders o ON o.o_custkey = c.c_custkey "
        "JOIN lineitem l ON l.l_orderkey = o.o_orderkey "
        "GROUP BY 1, 2"
    ),
    "agg_month_shipmode_revenue": (
        "CREATE TABLE agg_month_shipmode_revenue AS "
        "SELECT date_trunc('month', l.l_shipdate) AS month_bucket, "
        "       l.l_shipmode AS shipmode, "
        "       sum(l.l_extendedprice * (1 - l.l_discount)) AS revenue "
        "FROM lineitem l "
        "GROUP BY 1, 2"
    ),
    "agg_customer_year_revenue": (
        "CREATE TABLE agg_customer_year_revenue AS "
        "SELECT year(o.o_orderdate) AS revenue_year, "
        "       c.c_custkey, "
        "       sum(l.l_extendedprice * (1 - l.l_discount)) AS revenue "
        "FROM customer c "
        "JOIN orders o ON o.o_custkey = c.c_custkey "
        "JOIN lineitem l ON l.l_orderkey = o.o_orderkey "
        "GROUP BY 1, 2"
    ),
    "agg_unused_priority_only": (
        "CREATE TABLE agg_unused_priority_only AS "
        "SELECT o.o_orderpriority, count(*) AS order_count "
        "FROM orders o "
        "GROUP BY 1"
    ),
}

PREAGGREGATION_WORKLOAD_MANIFEST = {
    "schema_lineage": "TPC-H-inspired customer/orders/lineitem local workload",
    "candidate_preaggregations": tuple(sorted(PREAGGREGATION_CANDIDATES)),
    "workload_notes": (
        "Quarter revenue by customer segment",
        "Monthly revenue by ship mode",
        "Top customers by yearly revenue",
    ),
    "repetitions": 4,
}


ORIGINAL_QUERY_SQL = '''
WITH revenue AS (
  SELECT date_trunc('quarter', o.o_orderdate) AS quarter_bucket,
         c.c_mktsegment AS segment,
         sum(l.l_extendedprice * (1 - l.l_discount)) AS revenue
  FROM customer c
  JOIN orders o ON o.o_custkey = c.c_custkey
  JOIN lineitem l ON l.l_orderkey = o.o_orderkey
  WHERE c.c_mktsegment IN ('BUILDING', 'AUTOMOBILE', 'HOUSEHOLD')
  GROUP BY 1, 2
),
order_counts AS (
  SELECT date_trunc('quarter', o.o_orderdate) AS quarter_bucket,
         c.c_mktsegment AS segment,
         count(DISTINCT o.o_orderkey) AS order_count
  FROM customer c
  JOIN orders o ON o.o_custkey = c.c_custkey
  JOIN lineitem l ON l.l_orderkey = o.o_orderkey
  WHERE c.c_mktsegment IN ('BUILDING', 'AUTOMOBILE', 'HOUSEHOLD')
  GROUP BY 1, 2
)
SELECT r.quarter_bucket, r.segment, r.revenue, o.order_count
FROM revenue r
JOIN order_counts o USING (quarter_bucket, segment)
ORDER BY quarter_bucket, segment
'''.strip()

QUERY_REWRITE_MANIFEST = {
    "schema_lineage": "TPC-H-inspired customer/orders/lineitem local workload",
    "query_goal": "Fuse repeated scans of the same join into one grouped aggregation while preserving results and ordering.",
    "result_order_required": True,
    "repetitions": 4,
}


def build_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    con.execute("PRAGMA threads=1")
    con.execute(
        f\"\"\"
        CREATE TABLE customer AS
        SELECT i AS c_custkey,
               'Customer #' || i AS c_name,
               CASE i % 5
                 WHEN 0 THEN 'BUILDING'
                 WHEN 1 THEN 'AUTOMOBILE'
                 WHEN 2 THEN 'HOUSEHOLD'
                 WHEN 3 THEN 'FURNITURE'
                 ELSE 'MACHINERY'
               END AS c_mktsegment,
               i % 25 AS c_nationkey
        FROM range(1, {CUSTOMER_COUNT + 1}) t(i)
        \"\"\"
    )
    con.execute(
        f\"\"\"
        CREATE TABLE orders AS
        SELECT i AS o_orderkey,
               1 + ((i * 17) % {CUSTOMER_COUNT}) AS o_custkey,
               DATE '1995-01-01' + (((i * 13) % 1460) * INTERVAL 1 DAY) AS o_orderdate,
               100 + (((i * 37) % 100000) / 10.0) AS o_totalprice,
               CASE i % 5
                 WHEN 0 THEN '1-URGENT'
                 WHEN 1 THEN '2-HIGH'
                 WHEN 2 THEN '3-MEDIUM'
                 WHEN 3 THEN '4-NOT SPECIFIED'
                 ELSE '5-LOW'
               END AS o_orderpriority
        FROM range(1, {ORDER_COUNT + 1}) t(i)
        \"\"\"
    )
    con.execute(
        f\"\"\"
        CREATE TABLE lineitem AS
        SELECT i AS l_lineitemkey,
               1 + ((i * 7) % {ORDER_COUNT}) AS l_orderkey,
               1 + ((i * 11) % 50000) AS l_partkey,
               1 + ((i * 13) % 10000) AS l_suppkey,
               1 + ((i * 5) % 50) AS l_quantity,
               10 + (((i * 19) % 100000) / 20.0) AS l_extendedprice,
               (((i * 3) % 10) / 100.0) AS l_discount,
               DATE '1995-01-01' + (((i * 29) % 1460) * INTERVAL 1 DAY) AS l_shipdate,
               CASE i % 5
                 WHEN 0 THEN 'AIR'
                 WHEN 1 THEN 'MAIL'
                 WHEN 2 THEN 'RAIL'
                 WHEN 3 THEN 'TRUCK'
                 ELSE 'SHIP'
               END AS l_shipmode
        FROM range(1, {LINEITEM_COUNT + 1}) t(i)
        \"\"\"
    )
    return con


def normalize_name_list(value: Any, key: str) -> list[str]:
    if isinstance(value, dict):
        if key not in value:
            raise ValueError(f"missing {key}")
        value = value[key]
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{key} must be a list or tuple")
    out: list[str] = []
    seen = set()
    for item in value:
        name = str(item)
        if name not in seen:
            out.append(name)
            seen.add(name)
    return out


def compare_results(lhs: list[tuple[Any, ...]], rhs: list[tuple[Any, ...]], tol: float = 1e-6) -> bool:
    if len(lhs) != len(rhs):
        return False
    for left_row, right_row in zip(lhs, rhs):
        if len(left_row) != len(right_row):
            return False
        for left_value, right_value in zip(left_row, right_row):
            if isinstance(left_value, float) or isinstance(right_value, float):
                if not math.isfinite(float(left_value)) or not math.isfinite(float(right_value)):
                    return False
                if abs(float(left_value) - float(right_value)) > tol:
                    return False
            else:
                if left_value != right_value:
                    return False
    return True


def _report_quarter_segment(con: duckdb.DuckDBPyConnection, use_aggregate: bool) -> list[tuple[Any, ...]]:
    if use_aggregate:
        return con.execute(
            "SELECT quarter_bucket, segment, revenue "
            "FROM agg_quarter_segment_revenue "
            "ORDER BY quarter_bucket, segment"
        ).fetchall()
    return con.execute(
        "SELECT date_trunc('quarter', o.o_orderdate) AS quarter_bucket, "
        "       c.c_mktsegment AS segment, "
        "       sum(l.l_extendedprice * (1 - l.l_discount)) AS revenue "
        "FROM customer c "
        "JOIN orders o ON o.o_custkey = c.c_custkey "
        "JOIN lineitem l ON l.l_orderkey = o.o_orderkey "
        "GROUP BY 1, 2 "
        "ORDER BY quarter_bucket, segment"
    ).fetchall()


def _report_month_shipmode(con: duckdb.DuckDBPyConnection, use_aggregate: bool) -> list[tuple[Any, ...]]:
    if use_aggregate:
        return con.execute(
            "SELECT month_bucket, shipmode, revenue "
            "FROM agg_month_shipmode_revenue "
            "WHERE month_bucket >= DATE '1997-01-01' "
            "ORDER BY month_bucket, shipmode"
        ).fetchall()
    return con.execute(
        "SELECT date_trunc('month', l.l_shipdate) AS month_bucket, "
        "       l.l_shipmode AS shipmode, "
        "       sum(l.l_extendedprice * (1 - l.l_discount)) AS revenue "
        "FROM lineitem l "
        "WHERE l.l_shipdate >= DATE '1997-01-01' "
        "GROUP BY 1, 2 "
        "ORDER BY month_bucket, shipmode"
    ).fetchall()


def _report_customer_year(con: duckdb.DuckDBPyConnection, use_aggregate: bool) -> list[tuple[Any, ...]]:
    if use_aggregate:
        return con.execute(
            "SELECT revenue_year, c_custkey, revenue "
            "FROM agg_customer_year_revenue "
            "WHERE revenue_year = 1998 "
            "ORDER BY revenue DESC, c_custkey "
            "LIMIT 100"
        ).fetchall()
    return con.execute(
        "SELECT year(o.o_orderdate) AS revenue_year, "
        "       c.c_custkey, "
        "       sum(l.l_extendedprice * (1 - l.l_discount)) AS revenue "
        "FROM customer c "
        "JOIN orders o ON o.o_custkey = c.c_custkey "
        "JOIN lineitem l ON l.l_orderkey = o.o_orderkey "
        "GROUP BY 1, 2 "
        "HAVING year(o.o_orderdate) = 1998 "
        "ORDER BY revenue DESC, c.c_custkey "
        "LIMIT 100"
    ).fetchall()


def run_index_workload(con: duckdb.DuckDBPyConnection) -> float:
    start_time = time.perf_counter()
    for customer_key in CUSTOMER_KEYS:
        con.execute(
            "SELECT sum(o_totalprice) "
            "FROM orders "
            "WHERE o_custkey = ? AND o_orderdate >= DATE '1997-01-01'",
            [customer_key],
        ).fetchone()
    for order_key in ORDER_KEYS:
        con.execute(
            "SELECT sum(l_extendedprice * (1 - l_discount)) "
            "FROM lineitem "
            "WHERE l_orderkey = ?",
            [order_key],
        ).fetchone()
    for customer_key in CUSTOMER_KEYS[:120]:
        con.execute(
            "SELECT count(*) "
            "FROM customer c "
            "JOIN orders o ON c.c_custkey = o.o_custkey "
            "WHERE c.c_custkey = ? AND o.o_orderpriority = '1-URGENT'",
            [customer_key],
        ).fetchone()
    return time.perf_counter() - start_time


def measure_index_design(selected_indexes: list[str]) -> dict[str, float | int]:
    unknown = [name for name in selected_indexes if name not in INDEX_CANDIDATES]
    if unknown:
        raise ValueError(f"unknown index names: {unknown}")
    con = build_connection()
    start_setup = time.perf_counter()
    for name in selected_indexes:
        con.execute(INDEX_CANDIDATES[name])
    setup_runtime = time.perf_counter() - start_setup
    run_index_workload(con)
    workload_runtime = 0.0
    for _ in range(int(INDEX_WORKLOAD_MANIFEST["repetitions"])):
        workload_runtime += run_index_workload(con)
    return {
        "setup_runtime_s": float(setup_runtime),
        "workload_runtime_s": float(workload_runtime),
        "total_runtime_s": float(setup_runtime + workload_runtime),
        "selected_index_count": len(selected_indexes),
    }


def measure_query_rewrite(sql: str) -> dict[str, Any]:
    sql = str(sql).strip()
    if not sql:
        raise ValueError("query must not be empty")
    baseline_con = build_connection()
    candidate_con = build_connection()
    baseline_rows = baseline_con.execute(ORIGINAL_QUERY_SQL).fetchall()
    candidate_rows = candidate_con.execute(sql).fetchall()
    if not compare_results(candidate_rows, baseline_rows):
        raise ValueError("candidate query result does not match the baseline result")

    baseline_con.execute(ORIGINAL_QUERY_SQL).fetchall()
    baseline_start = time.perf_counter()
    for _ in range(int(QUERY_REWRITE_MANIFEST["repetitions"])):
        baseline_con.execute(ORIGINAL_QUERY_SQL).fetchall()
    baseline_runtime = time.perf_counter() - baseline_start

    candidate_con.execute(sql).fetchall()
    candidate_start = time.perf_counter()
    for _ in range(int(QUERY_REWRITE_MANIFEST["repetitions"])):
        candidate_rows = candidate_con.execute(sql).fetchall()
    candidate_runtime = time.perf_counter() - candidate_start

    return {
        "baseline_runtime_s": float(baseline_runtime),
        "candidate_runtime_s": float(candidate_runtime),
        "row_count": len(candidate_rows),
    }


def _run_preaggregation_reports(con: duckdb.DuckDBPyConnection, selected: set[str]) -> tuple[float, tuple[list[tuple[Any, ...]], ...]]:
    start_time = time.perf_counter()
    result_a = _report_quarter_segment(con, "agg_quarter_segment_revenue" in selected)
    result_b = _report_month_shipmode(con, "agg_month_shipmode_revenue" in selected)
    result_c = _report_customer_year(con, "agg_customer_year_revenue" in selected)
    runtime = time.perf_counter() - start_time
    return runtime, (result_a, result_b, result_c)


def measure_preaggregation_design(selected_preaggregations: list[str]) -> dict[str, float | int]:
    unknown = [name for name in selected_preaggregations if name not in PREAGGREGATION_CANDIDATES]
    if unknown:
        raise ValueError(f"unknown pre-aggregation names: {unknown}")
    if not selected_preaggregations:
        con = build_connection()
        _run_preaggregation_reports(con, set())
        repeated_runtime = 0.0
        for _ in range(int(PREAGGREGATION_WORKLOAD_MANIFEST["repetitions"])):
            extra_runtime, _ = _run_preaggregation_reports(con, set())
            repeated_runtime += extra_runtime
        return {
            "setup_runtime_s": 0.0,
            "candidate_workload_runtime_s": float(repeated_runtime),
            "candidate_total_runtime_s": float(repeated_runtime),
            "baseline_total_runtime_s": float(repeated_runtime),
            "selected_preaggregation_count": 0,
        }
    baseline_con = build_connection()
    candidate_con = build_connection()
    start_setup = time.perf_counter()
    for name in selected_preaggregations:
        candidate_con.execute(PREAGGREGATION_CANDIDATES[name])
    setup_runtime = time.perf_counter() - start_setup

    _, baseline_results = _run_preaggregation_reports(baseline_con, set())
    _, candidate_results = _run_preaggregation_reports(candidate_con, set(selected_preaggregations))
    if any(not compare_results(left, right) for left, right in zip(candidate_results, baseline_results)):
        raise ValueError("candidate pre-aggregation selection changed the query results")

    _run_preaggregation_reports(baseline_con, set())
    _run_preaggregation_reports(candidate_con, set(selected_preaggregations))

    repeated_baseline_runtime = 0.0
    for _ in range(int(PREAGGREGATION_WORKLOAD_MANIFEST["repetitions"])):
        extra_runtime, _ = _run_preaggregation_reports(baseline_con, set())
        repeated_baseline_runtime += extra_runtime

    repeated_candidate_runtime = 0.0
    for _ in range(int(PREAGGREGATION_WORKLOAD_MANIFEST["repetitions"])):
        extra_runtime, _ = _run_preaggregation_reports(candidate_con, set(selected_preaggregations))
        repeated_candidate_runtime += extra_runtime

    candidate_total_runtime = setup_runtime + repeated_candidate_runtime
    baseline_total_runtime = repeated_baseline_runtime
    return {
        "setup_runtime_s": float(setup_runtime),
        "candidate_workload_runtime_s": float(repeated_candidate_runtime),
        "candidate_total_runtime_s": float(candidate_total_runtime),
        "baseline_total_runtime_s": float(baseline_total_runtime),
        "selected_preaggregation_count": len(selected_preaggregations),
    }
"""


README_TEMPLATE = """\
# __TITLE__

__SHORT__

## Provenance

- Provenance class: `traceable local workload with DuckDB/TPC-H schema lineage`
- Engine lineage: `DuckDB`
- Data asset: benchmark-local deterministic SQL-generated tables
- Full provenance note: see `references/source_manifest.md`

## File Layout

- `Task.md`: task contract and scoring rules.
- `Task_zh-CN.md`: Chinese translation.
- `README_zh-CN.md`: Chinese overview.
- `scripts/init.py`: initial candidate file exposed to agents.
- `baseline/solution.py`: reference implementation.
- `runtime/problem.py`: task-local interface to the frozen workload.
- `verification/evaluator.py`: evaluator entry.
- `references/source_manifest.md`: provenance and authenticity notes.

## Quick Run

From repository root:

```bash
.venv/bin/python benchmarks/ComputerSystems/__SLUG__/verification/evaluator.py \\
  benchmarks/ComputerSystems/__SLUG__/scripts/init.py \\
  --metrics-out /tmp/__SLUG___metrics.json
```
"""


README_ZH_TEMPLATE = """\
# __TITLE__

__SHORT__

## 说明

- 数据来源类型：`traceable local workload with DuckDB/TPC-H schema lineage`
- 执行引擎：`DuckDB`
- 数据资产：本 benchmark 内部固定的 deterministic SQL 生成表
- 完整来源说明见 `references/source_manifest.md`
"""


TASK_INDEX = """\
# __TITLE__ Task

## Objective

__SHORT__

## Submission Contract

Submit one Python file that defines:

```python
def select_indexes(workload_manifest):
    ...
```

Return a list of candidate index names from the whitelist in `workload_manifest["candidate_indexes"]`.
A dict with key `indexes` is also accepted.

## Evaluation

The evaluator will:

1. Build the frozen DuckDB workload.
2. Create the selected indexes.
3. Run the fixed lookup workload four times.
4. Record the candidate total runtime and log the no-index baseline for context.

## Metrics

- `combined_score`: `-candidate_total_runtime_s`
- `valid`: `1.0` only if every selected index name is valid and execution succeeds
- `candidate_total_runtime_s`
- `baseline_total_runtime_s`
- `candidate_setup_runtime_s`
- `candidate_workload_runtime_s`
"""


TASK_REWRITE = """\
# __TITLE__ Task

## Objective

__SHORT__

## Submission Contract

Submit one Python file that defines:

```python
def rewrite_query(sql, workload_manifest):
    ...
```

Return a rewritten SQL string. A dict with key `sql` is also accepted.

## Evaluation

The evaluator will:

1. Build the frozen DuckDB workload.
2. Execute the original SQL to get the reference result.
3. Execute your rewritten SQL and verify exact result equivalence.
4. Time the candidate query over repeated runs and log the baseline rewrite runtime for context.

## Metrics

- `combined_score`: `-candidate_runtime_s`
- `valid`: `1.0` only if the rewritten query preserves results
- `candidate_runtime_s`
- `baseline_runtime_s`
- `row_count`
"""


TASK_PREAGG = """\
# __TITLE__ Task

## Objective

__SHORT__

## Submission Contract

Submit one Python file that defines:

```python
def select_preaggregations(workload_manifest):
    ...
```

Return a list of candidate pre-aggregation names from the whitelist in `workload_manifest["candidate_preaggregations"]`.
A dict with key `preaggregations` is also accepted.

## Evaluation

The evaluator will:

1. Build the frozen DuckDB workload.
2. Create the selected pre-aggregation tables.
3. Run the fixed reporting workload and verify result equivalence.
4. Measure candidate total runtime as setup cost plus repeated report execution, and log the baseline for context.

## Metrics

- `combined_score`: `-candidate_total_runtime_s`
- `valid`: `1.0` only if all selected names are valid and results stay unchanged
- `candidate_total_runtime_s`
- `baseline_total_runtime_s`
- `candidate_setup_runtime_s`
- `candidate_workload_runtime_s`
"""


TASK_INDEX_ZH = """\
# __TITLE__ 任务

## 目标

__SHORT__

## 提交接口

提交一个 Python 文件，定义：

```python
def select_indexes(workload_manifest):
    ...
```

返回值必须是 whitelist 中的索引名列表。也接受包含 `indexes` 字段的字典。

## 评测方式

评测器会：

1. 构建固定的 DuckDB workload。
2. 创建所选索引。
3. 固定重复执行查询 workload 四次。
4. 记录候选总运行时间，并把无索引 baseline 作为诊断信息一并输出。

## 指标

- `combined_score`：`-candidate_total_runtime_s`
- `valid`：只有索引名合法且执行成功时才为 `1.0`
- `candidate_total_runtime_s`
- `baseline_total_runtime_s`
- `candidate_setup_runtime_s`
- `candidate_workload_runtime_s`
"""


TASK_REWRITE_ZH = """\
# __TITLE__ 任务

## 目标

__SHORT__

## 提交接口

提交一个 Python 文件，定义：

```python
def rewrite_query(sql, workload_manifest):
    ...
```

返回值必须是重写后的 SQL 字符串。也接受包含 `sql` 字段的字典。

## 评测方式

评测器会：

1. 构建固定的 DuckDB workload。
2. 执行原始 SQL，得到参考结果。
3. 执行候选重写 SQL，并严格检查结果等价。
4. 多次计时候选查询，并把 baseline 重写的运行时间作为诊断信息输出。

## 指标

- `combined_score`：`-candidate_runtime_s`
- `valid`：只有重写 SQL 保持结果不变时才为 `1.0`
- `candidate_runtime_s`
- `baseline_runtime_s`
- `row_count`
"""


TASK_PREAGG_ZH = """\
# __TITLE__ 任务

## 目标

__SHORT__

## 提交接口

提交一个 Python 文件，定义：

```python
def select_preaggregations(workload_manifest):
    ...
```

返回值必须是 whitelist 中的预聚合表名列表。也接受包含 `preaggregations` 字段的字典。

## 评测方式

评测器会：

1. 构建固定的 DuckDB workload。
2. 创建所选预聚合表。
3. 运行固定 reporting workload，并检查结果是否保持一致。
4. 记录候选总运行时间，并把 baseline 总运行时间作为诊断信息输出。

## 指标

- `combined_score`：`-candidate_total_runtime_s`
- `valid`：只有名称合法且结果保持不变时才为 `1.0`
- `candidate_total_runtime_s`
- `baseline_total_runtime_s`
- `candidate_setup_runtime_s`
- `candidate_workload_runtime_s`
"""


INIT_INDEX = """\
#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _ensure_import_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            ps = str(parent)
            if ps not in sys.path:
                sys.path.insert(0, ps)
            return
    benchmark_root = here.parents[1]
    ps = str(benchmark_root)
    if ps not in sys.path:
        sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.ComputerSystems.__SLUG__.baseline.solution import select_indexes as _baseline_select_indexes
    from benchmarks.ComputerSystems.__SLUG__.runtime.problem import WORKLOAD_MANIFEST, evaluate_selection
except ModuleNotFoundError:
    from baseline.solution import select_indexes as _baseline_select_indexes
    from runtime.problem import WORKLOAD_MANIFEST, evaluate_selection


# EVOLVE-BLOCK-START
def select_indexes(workload_manifest):
    return _baseline_select_indexes(workload_manifest)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    print(evaluate_selection(select_indexes(WORKLOAD_MANIFEST)))
"""


INIT_REWRITE = """\
#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _ensure_import_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            ps = str(parent)
            if ps not in sys.path:
                sys.path.insert(0, ps)
            return
    benchmark_root = here.parents[1]
    ps = str(benchmark_root)
    if ps not in sys.path:
        sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.ComputerSystems.__SLUG__.baseline.solution import rewrite_query as _baseline_rewrite_query
    from benchmarks.ComputerSystems.__SLUG__.runtime.problem import ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST, evaluate_query
except ModuleNotFoundError:
    from baseline.solution import rewrite_query as _baseline_rewrite_query
    from runtime.problem import ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST, evaluate_query


# EVOLVE-BLOCK-START
def rewrite_query(sql, workload_manifest):
    return _baseline_rewrite_query(sql, workload_manifest)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    print(evaluate_query(rewrite_query(ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST)))
"""


INIT_PREAGG = """\
#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _ensure_import_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            ps = str(parent)
            if ps not in sys.path:
                sys.path.insert(0, ps)
            return
    benchmark_root = here.parents[1]
    ps = str(benchmark_root)
    if ps not in sys.path:
        sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.ComputerSystems.__SLUG__.baseline.solution import select_preaggregations as _baseline_select_preaggregations
    from benchmarks.ComputerSystems.__SLUG__.runtime.problem import WORKLOAD_MANIFEST, evaluate_selection
except ModuleNotFoundError:
    from baseline.solution import select_preaggregations as _baseline_select_preaggregations
    from runtime.problem import WORKLOAD_MANIFEST, evaluate_selection


# EVOLVE-BLOCK-START
def select_preaggregations(workload_manifest):
    return _baseline_select_preaggregations(workload_manifest)
# EVOLVE-BLOCK-END


if __name__ == "__main__":
    print(evaluate_selection(select_preaggregations(WORKLOAD_MANIFEST)))
"""


BASELINE_INDEX = """\
from __future__ import annotations


def select_indexes(workload_manifest):
    return []
"""


BASELINE_REWRITE = """\
from __future__ import annotations


def rewrite_query(sql, workload_manifest):
    return sql
"""


BASELINE_PREAGG = """\
from __future__ import annotations


def select_preaggregations(workload_manifest):
    return []
"""


RUNTIME_INDEX = """\
from __future__ import annotations

from .duckdb_local_workload import INDEX_WORKLOAD_MANIFEST, measure_index_design, normalize_name_list


WORKLOAD_MANIFEST = dict(INDEX_WORKLOAD_MANIFEST)


def load_instance():
    return dict(WORKLOAD_MANIFEST)


def evaluate_selection(selection):
    return measure_index_design(normalize_name_list(selection, "indexes"))
"""


RUNTIME_REWRITE = """\
from __future__ import annotations

from .duckdb_local_workload import ORIGINAL_QUERY_SQL, QUERY_REWRITE_MANIFEST, measure_query_rewrite


WORKLOAD_MANIFEST = dict(QUERY_REWRITE_MANIFEST)


def load_instance():
    return {"sql": ORIGINAL_QUERY_SQL, "manifest": dict(WORKLOAD_MANIFEST)}


def evaluate_query(value):
    if isinstance(value, dict):
        if "sql" not in value:
            raise ValueError("missing sql")
        value = value["sql"]
    return measure_query_rewrite(str(value))
"""


RUNTIME_PREAGG = """\
from __future__ import annotations

from .duckdb_local_workload import PREAGGREGATION_WORKLOAD_MANIFEST, measure_preaggregation_design, normalize_name_list


WORKLOAD_MANIFEST = dict(PREAGGREGATION_WORKLOAD_MANIFEST)


def load_instance():
    return dict(WORKLOAD_MANIFEST)


def evaluate_selection(selection):
    return measure_preaggregation_design(normalize_name_list(selection, "preaggregations"))
"""


EVALUATOR_INDEX = """\
from __future__ import annotations

import argparse
import json
import math
import runpy
import traceback
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    return Path.cwd().resolve()


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_path() -> None:
    import sys

    for p in (_repo_root(), _benchmark_root()):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.ComputerSystems.__SLUG__.baseline.solution import select_indexes as baseline_select_indexes
    from benchmarks.ComputerSystems.__SLUG__.runtime.problem import WORKLOAD_MANIFEST, evaluate_selection
except ModuleNotFoundError:
    from baseline.solution import select_indexes as baseline_select_indexes
    from runtime.problem import WORKLOAD_MANIFEST, evaluate_selection


def evaluate(program_path: str):
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_total_runtime_s": 0.0,
        "baseline_total_runtime_s": 0.0,
        "candidate_setup_runtime_s": 0.0,
        "candidate_workload_runtime_s": 0.0,
    }
    artifacts = {}
    namespace = runpy.run_path(str(Path(program_path).expanduser().resolve()), run_name="candidate_program")
    select_indexes = namespace.get("select_indexes")
    if not callable(select_indexes):
        artifacts["error_message"] = "candidate must define select_indexes(workload_manifest)"
        return metrics, artifacts
    try:
        baseline = evaluate_selection(baseline_select_indexes(WORKLOAD_MANIFEST))
        candidate = evaluate_selection(select_indexes(WORKLOAD_MANIFEST))
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts
    candidate_total = float(candidate["total_runtime_s"])
    baseline_total = float(baseline["total_runtime_s"])
    if not math.isfinite(candidate_total) or candidate_total <= 0:
        artifacts["error_message"] = "candidate runtime is invalid"
        return metrics, artifacts
    metrics["valid"] = 1.0
    metrics["candidate_total_runtime_s"] = candidate_total
    metrics["baseline_total_runtime_s"] = baseline_total
    metrics["candidate_setup_runtime_s"] = float(candidate["setup_runtime_s"])
    metrics["candidate_workload_runtime_s"] = float(candidate["workload_runtime_s"])
    metrics["combined_score"] = -candidate_total
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    parser.add_argument("--metrics-out", default="metrics.json")
    args = parser.parse_args()
    metrics, artifacts = evaluate(args.program)
    Path(args.metrics_out).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if artifacts:
        Path("artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
"""


EVALUATOR_REWRITE = """\
from __future__ import annotations

import argparse
import json
import math
import runpy
import traceback
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    return Path.cwd().resolve()


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_path() -> None:
    import sys

    for p in (_repo_root(), _benchmark_root()):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.ComputerSystems.__SLUG__.baseline.solution import rewrite_query as baseline_rewrite_query
    from benchmarks.ComputerSystems.__SLUG__.runtime.problem import ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST, evaluate_query
except ModuleNotFoundError:
    from baseline.solution import rewrite_query as baseline_rewrite_query
    from runtime.problem import ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST, evaluate_query


def evaluate(program_path: str):
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_runtime_s": 0.0,
        "baseline_runtime_s": 0.0,
        "row_count": 0.0,
    }
    artifacts = {}
    namespace = runpy.run_path(str(Path(program_path).expanduser().resolve()), run_name="candidate_program")
    rewrite_query = namespace.get("rewrite_query")
    if not callable(rewrite_query):
        artifacts["error_message"] = "candidate must define rewrite_query(sql, workload_manifest)"
        return metrics, artifacts
    try:
        baseline = evaluate_query(baseline_rewrite_query(ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST))
        candidate = evaluate_query(rewrite_query(ORIGINAL_QUERY_SQL, WORKLOAD_MANIFEST))
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts
    candidate_runtime = float(candidate["candidate_runtime_s"])
    baseline_runtime = float(baseline["candidate_runtime_s"])
    if not math.isfinite(candidate_runtime) or candidate_runtime <= 0:
        artifacts["error_message"] = "candidate runtime is invalid"
        return metrics, artifacts
    metrics["valid"] = 1.0
    metrics["candidate_runtime_s"] = candidate_runtime
    metrics["baseline_runtime_s"] = baseline_runtime
    metrics["row_count"] = float(candidate["row_count"])
    metrics["combined_score"] = -candidate_runtime
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    parser.add_argument("--metrics-out", default="metrics.json")
    args = parser.parse_args()
    metrics, artifacts = evaluate(args.program)
    Path(args.metrics_out).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if artifacts:
        Path("artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
"""


EVALUATOR_PREAGG = """\
from __future__ import annotations

import argparse
import json
import math
import runpy
import traceback
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "benchmarks").is_dir() and (parent / "frontier_eval").is_dir():
            return parent
    return Path.cwd().resolve()


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_path() -> None:
    import sys

    for p in (_repo_root(), _benchmark_root()):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


_ensure_import_path()

try:
    from benchmarks.ComputerSystems.__SLUG__.baseline.solution import select_preaggregations as baseline_select_preaggregations
    from benchmarks.ComputerSystems.__SLUG__.runtime.problem import WORKLOAD_MANIFEST, evaluate_selection
except ModuleNotFoundError:
    from baseline.solution import select_preaggregations as baseline_select_preaggregations
    from runtime.problem import WORKLOAD_MANIFEST, evaluate_selection


def evaluate(program_path: str):
    metrics = {
        "combined_score": -1e18,
        "valid": 0.0,
        "candidate_total_runtime_s": 0.0,
        "baseline_total_runtime_s": 0.0,
        "candidate_setup_runtime_s": 0.0,
        "candidate_workload_runtime_s": 0.0,
    }
    artifacts = {}
    namespace = runpy.run_path(str(Path(program_path).expanduser().resolve()), run_name="candidate_program")
    select_preaggregations = namespace.get("select_preaggregations")
    if not callable(select_preaggregations):
        artifacts["error_message"] = "candidate must define select_preaggregations(workload_manifest)"
        return metrics, artifacts
    try:
        baseline = evaluate_selection(baseline_select_preaggregations(WORKLOAD_MANIFEST))
        candidate = evaluate_selection(select_preaggregations(WORKLOAD_MANIFEST))
    except Exception:
        artifacts["error_message"] = traceback.format_exc()
        return metrics, artifacts
    candidate_total = float(candidate["candidate_total_runtime_s"])
    baseline_total = float(candidate["baseline_total_runtime_s"])
    if not math.isfinite(candidate_total) or candidate_total <= 0:
        artifacts["error_message"] = "candidate runtime is invalid"
        return metrics, artifacts
    metrics["valid"] = 1.0
    metrics["candidate_total_runtime_s"] = candidate_total
    metrics["baseline_total_runtime_s"] = baseline_total
    metrics["candidate_setup_runtime_s"] = float(candidate["setup_runtime_s"])
    metrics["candidate_workload_runtime_s"] = float(candidate["candidate_workload_runtime_s"])
    metrics["combined_score"] = -candidate_total
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    parser.add_argument("--metrics-out", default="metrics.json")
    args = parser.parse_args()
    metrics, artifacts = evaluate(args.program)
    Path(args.metrics_out).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if artifacts:
        Path("artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
"""


def render(template: str, **values: str) -> str:
    out = template
    for key, value in values.items():
        out = out.replace(f"__{key}__", value)
    return out


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).rstrip() + "\n", encoding="utf-8")


def frontier_eval_files() -> dict[str, str]:
    return {
        "frontier_eval/agent_files.txt": "Task.md\nTask_zh-CN.md\nREADME.md\nbaseline/solution.py\nruntime/problem.py\n",
        "frontier_eval/candidate_destination.txt": "scripts/init.py\n",
        "frontier_eval/constraints.txt": (
            "Edit only `scripts/init.py`.\n"
            "Modify only code between `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` in that file.\n"
            "Do not modify files under `baseline/`, `runtime/`, `references/`, or `verification/`.\n"
            "Keep outputs valid and finite.\n"
        ),
        "frontier_eval/eval_command.txt": "{python} verification/evaluator.py {candidate} --metrics-out metrics.json\n",
        "frontier_eval/eval_cwd.txt": ".\n",
        "frontier_eval/initial_program.txt": "scripts/init.py\n",
        "frontier_eval/readonly_files.txt": (
            "baseline/solution.py\n"
            "runtime/problem.py\n"
            "runtime/duckdb_local_workload.py\n"
            "verification/evaluator.py\n"
            "references/source_manifest.md\n"
        ),
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    domain_root = repo_root / "benchmarks" / "ComputerSystems"

    for task in TASKS:
        root = domain_root / task["slug"]
        values = {
            "TITLE": task["title"],
            "SHORT": task["short"],
            "SLUG": task["slug"],
        }
        write(root / "README.md", render(README_TEMPLATE, **values))
        write(root / "README_zh-CN.md", render(README_ZH_TEMPLATE, **values))
        write(root / "references" / "source_manifest.md", task["source_manifest"])
        write(root / "verification" / "requirements.txt", "duckdb\n")

        if task["kind"] == "index":
            write(root / "Task.md", render(TASK_INDEX, **values))
            write(root / "Task_zh-CN.md", render(TASK_INDEX_ZH, **values))
            write(root / "scripts" / "init.py", render(INIT_INDEX, **values))
            write(root / "baseline" / "solution.py", BASELINE_INDEX)
            write(root / "runtime" / "problem.py", RUNTIME_INDEX)
            write(root / "runtime" / "duckdb_local_workload.py", HELPER_TEXT)
            write(root / "verification" / "evaluator.py", render(EVALUATOR_INDEX, **values))
        elif task["kind"] == "rewrite":
            write(root / "Task.md", render(TASK_REWRITE, **values))
            write(root / "Task_zh-CN.md", render(TASK_REWRITE_ZH, **values))
            write(root / "scripts" / "init.py", render(INIT_REWRITE, **values))
            write(root / "baseline" / "solution.py", BASELINE_REWRITE)
            write(root / "runtime" / "problem.py", RUNTIME_REWRITE)
            write(root / "runtime" / "duckdb_local_workload.py", HELPER_TEXT)
            write(root / "verification" / "evaluator.py", render(EVALUATOR_REWRITE, **values))
        else:
            write(root / "Task.md", render(TASK_PREAGG, **values))
            write(root / "Task_zh-CN.md", render(TASK_PREAGG_ZH, **values))
            write(root / "scripts" / "init.py", render(INIT_PREAGG, **values))
            write(root / "baseline" / "solution.py", BASELINE_PREAGG)
            write(root / "runtime" / "problem.py", RUNTIME_PREAGG)
            write(root / "runtime" / "duckdb_local_workload.py", HELPER_TEXT)
            write(root / "verification" / "evaluator.py", render(EVALUATOR_PREAGG, **values))

        for relative, content in frontier_eval_files().items():
            write(root / relative, content)


if __name__ == "__main__":
    main()
