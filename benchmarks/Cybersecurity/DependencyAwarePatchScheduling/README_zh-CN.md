# 依赖感知的网络安全补丁调度

本基准研究离线补丁选择与整数时隙调度。调度必须同时满足补丁前置依赖、维护窗口、可再生资源容量、资产互斥、服务停机容量和累计停机预算等约束，并考虑回滚风险。

每个确定性实例包含资产、服务、可再生资源、漏洞和补丁。候选程序返回所选补丁的标识符与开始时隙；未出现在日程中的补丁视为未应用。

## 文件

- `Task.md`：英文候选任务说明。
- `Task_zh-CN.md`：简体中文候选任务说明。
- `scripts/init.py`：与基线行为一致的自包含起始求解器。
- `verification/problem.py`：确定性实例生成、基线求解器、验证器和原始目标计算。

## 必需 API

`verification.problem` 导出：

- `generate_instances(seed) -> list[dict]`
- `solve_random(instance) -> dict`
- `solve_baseline(instance) -> dict`
- `solve_reference(instance) -> dict`
- `validate_solution(instance, solution) -> tuple[bool, str]`
- `evaluate_solution(instance, solution) -> int | float`

每个种子生成一个小型、一个中型和一个大型实例。规划时域、实体数量、依赖密度、标识符和数组顺序均随种子确定性变化。生成器仅使用局部的确定性整数随机生成过程，并且不会调用任何求解器。

## 目标函数

需要最小化的原始指标是以微货币单位表示的总期望损失，包括：

1. 修复完成前累计的、经资产关键度调整的期望安全损失。
2. 已调度补丁造成的逐时隙业务停机损失。
3. 期望回滚损失。

概率采用百万分之一整数表示。每次概率乘法后均按四舍五入规则取整。评估器只返回严格为正的原始损失；`log2(baseline / candidate)` 归一化由基准框架负责。

## 基线

确定性对照求解器返回可行的空日程。起始求解器和基线按照依赖感知的收益密度排序，在最早可行时隙安排完整的前置补丁包，并且只保留能降低目标值的补丁包。

参考求解器会在五个补丁的小型实例上穷举全部依赖闭合的补丁子集和可行开始时间组合。中型和大型实例使用多种确定性优先级顺序及指定首个补丁的前瞻搜索。小型实例的精确结果用于审计解质量，中大型实例用于保留实际算法优化空间。

## 证据

NIST SP 800-40 Rev. 4 为在运营约束下开展基于风险的企业补丁规划提供依据。CISA BOD 22-01 为优先处理已有在野利用证据的漏洞和设置修复期限提供依据。benchmark 中的金额和依赖图是用于校准的合成数据，并非两份资料提供的实测值。

## 适用范围

该模型可复现且可独立验证，但仍是规划抽象。它不表示攻击者适应、紧急审批、工期不确定性、相关回滚故障、部分部署、未知依赖、实时事件响应或人员协调延迟。

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## 评测契约

验证器会独立重算 `verifier_recomputed_total_expected_monetary_loss_microunits`，候选方案需要将其最小化。
每个有效实例按照相对基线的 `log2` 改进计分，最终取所有实例分数的平均；
无效方案得分为 `-1e18`。

## 评测设计

问题设定：`离线批量`。到达模型：Each instance is a static planning batch: the complete vulnerability set, patch catalog, dependency graph, asset and service data, exploit-probability curves, capacities, maintenance windows, durations, and cost parameters are revealed before a schedule is submitted. No vulnerabilities, windows, or capacity changes arrive during execution. Benchmark instances are regenerated deterministically from fixed seeds, and the seed does not change in response to candidate behavior.

目标理由：Expected monetary loss is appropriate because patching is not valuable merely for maximizing patch count or minimizing completion time. It prices the security exposure retained by delaying or omitting patches while also charging for the business disruption and rollback exposure caused by applying them. Expressing all three components in a common monetary unit produces a continuous, auditable tradeoff and keeps feasibility rules separate from preferences. The raw objective is strictly lower-is-better and can be kept positive through instance construction, making it suitable for framework-owned log2_baseline_ratio normalization.

文献对齐：NIST SP 800-40 Rev. 4 frames enterprise patching as risk-based preventive maintenance that must be planned alongside operational constraints. CISA BOD 22-01 provides a concrete basis for prioritizing vulnerabilities with evidence of active exploitation and for modeling remediation deadlines. This benchmark turns those planning principles into a deterministic offline optimization problem; its synthetic monetary loss, rollback, resource, and downtime parameters are benchmark abstractions rather than values claimed by either source. It differs from classical makespan scheduling by allowing economically rational patch omission and by jointly enforcing dependency closure, maintenance calendars, renewable resources, and service downtime limits.

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
