# 任务

给定一批分析查询和固定的差分隐私总预算，请为每个查询分配一个非负 epsilon 值。

每个查询包含：

- `id`：查询标识符。
- `sensitivity`：用于确定性误差模型的敏感度。
- `business_value`：查询价值权重。
- `population_coverage`：覆盖人群比例或权重。
- `epsilon_min`：允许的最小隐私预算。
- `epsilon_max`：允许的最大隐私预算。
- `max_error`：允许的最大估计误差。
- `group`：用于公平性检查的人群组标签。

查询的估计误差为 `sensitivity / epsilon`。分配方案必须满足每个查询的上下界、每个查询的最大误差、总预算限制，以及基于组平均误差的公平性比例限制。

## 输出要求

返回一个只包含以下键的字典：

```python
{
  "allocations": {
    "query_id": epsilon
  }
}
```

分配映射必须精确包含所有要求的查询 ID，并且 epsilon 必须是有限数值。

## 目标

通过可行性检查后，验证器会计算一个正向原始效用指标。数值越大越好。该指标奖励有用的分析预算，并惩罚估计误差。归一化由 benchmark 框架处理。

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## 输入 Schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "queries",
    "epsilon_total",
    "fairness"
  ],
  "properties": {
    "queries": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "sensitivity",
          "business_value",
          "population_coverage",
          "epsilon_min",
          "epsilon_max",
          "max_error",
          "group"
        ],
        "properties": {
          "id": {
            "type": "string"
          },
          "sensitivity": {
            "type": "number",
            "minimum": 0
          },
          "business_value": {
            "type": "number",
            "minimum": 0
          },
          "population_coverage": {
            "type": "number",
            "minimum": 0
          },
          "epsilon_min": {
            "type": "number",
            "minimum": 0
          },
          "epsilon_max": {
            "type": "number",
            "minimum": 0
          },
          "max_error": {
            "type": "number",
            "minimum": 0
          },
          "group": {
            "type": "string"
          }
        }
      }
    },
    "epsilon_total": {
      "type": "number",
      "minimum": 0
    },
    "fairness": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "max_group_error_ratio"
      ],
      "properties": {
        "max_group_error_ratio": {
          "type": "number",
          "minimum": 1
        }
      }
    }
  }
}
```

## 输出 Schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "allocations"
  ],
  "properties": {
    "allocations": {
      "type": "object",
      "additionalProperties": true
    }
  }
}
```

## 约束与目标

输出必须满足上文全部硬约束。冻结验证器会独立检查可行性并重算
`Verifier-owned positive raw utility: 1.0 plus the sum over queries of business_value * population_coverage * log1p(epsilon) minus deterministic error penalties, evaluated only after all feasibility checks pass.`；优化目标是将这个严格为正的原始指标最大化。
有效实例使用相对基线的 `log2` 改进值，并取平均；无效方案得分为 `-1e18`。
问题设定为 `离线批量`。目标设计理由：The primary objective is appropriate because privacy budget is a scarce resource and the economically relevant decision is the feasible allocation that preserves the most weighted analytics utility while controlling estimation error. Accuracy and fairness are hard feasibility requirements so the objective cannot trade them away beyond accepted policy limits.
文献对齐：The supplied brief aligns with differential-privacy budget-allocation work at the level of allocating limited privacy loss across multiple analytics queries and recomputing privacy loss and error from first principles. This benchmark differs by making the task an offline batch portfolio optimization problem with explicit business values, population coverage, fairness constraints, and a structured candidate output rather than an interactive privacy accountant or a single-query mechanism design task.
<!-- BENCHGEN-PUBLIC-CONTRACT-END -->
