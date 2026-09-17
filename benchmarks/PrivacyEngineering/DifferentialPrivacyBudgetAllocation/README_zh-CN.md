# 面向业务分析的差分隐私预算分配

本任务要求在一批分析查询之间分配固定的差分隐私预算。每个查询都有敏感度、业务价值、覆盖人群比例、epsilon 上下界、最大误差限制以及所属人群组。解需要为每个查询返回一个 epsilon 分配值。

验证器会先检查硬约束：查询 ID 是否完整且精确匹配、分配值是否为有限数字、是否满足每个查询的上下界、总预算、最大估计误差，以及组级平均误差差异限制。只有可行解才会计算由验证器定义的正向原始效用指标。

## 参赛接口

在 `scripts/init.py` 中实现 `solve(instance)`。

输入字段：

- `queries`：查询对象列表。
- `epsilon_total`：总隐私预算。
- `fairness.max_group_error_ratio`：最大允许的组间平均误差比值。

返回：

```python
{"allocations": {query_id: epsilon, ...}}
```

输出必须精确包含实例中的所有查询 ID。

## 评分

对可行解，原始指标严格为正，且越大越好。该指标结合了加权业务价值和确定性的估计误差惩罚。无效或不可行输出由框架赋予无效分数。

框架会在验证器外部使用 `log2_baseline_ratio` 进行归一化。

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## 评测契约

验证器会独立重算 `Verifier-owned positive raw utility: 1.0 plus the sum over queries of business_value * population_coverage * log1p(epsilon) minus deterministic error penalties, evaluated only after all feasibility checks pass.`，候选方案需要将其最大化。
每个有效实例按照相对基线的 `log2` 改进计分，最终取所有实例分数的平均；
无效方案得分为 `-1e18`。

## 评测设计

问题设定：`离线批量`。到达模型：All analytics-query portfolios are generated deterministically from fixed seeds before solving. A candidate receives a complete static instance containing query sensitivities, business values, population coverage, group memberships, bounds, fairness thresholds, accuracy requirements, and total budget, then returns one structured allocation for that instance.

目标理由：The primary objective is appropriate because privacy budget is a scarce resource and the economically relevant decision is the feasible allocation that preserves the most weighted analytics utility while controlling estimation error. Accuracy and fairness are hard feasibility requirements so the objective cannot trade them away beyond accepted policy limits.

文献对齐：The supplied brief aligns with differential-privacy budget-allocation work at the level of allocating limited privacy loss across multiple analytics queries and recomputing privacy loss and error from first principles. This benchmark differs by making the task an offline batch portfolio optimization problem with explicit business values, population coverage, fairness constraints, and a structured candidate output rather than an interactive privacy accountant or a single-query mechanism design task.

本地执行只适用于已经审核的代码：

```bash
python verification/evaluator.py scripts/init.py --local
```

正式发布评测需要 Docker 和固定摘要的运行镜像：

```bash
docker pull python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
python verification/evaluator.py scripts/init.py
```
<!-- BENCHGEN-PUBLIC-CONTRACT-END -->
