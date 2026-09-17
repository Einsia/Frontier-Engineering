# 任务：动态 Edge Service 副本放置与路由

改进 `scripts/init.py` 的 EVOLVE-BLOCK。每个五分钟时段，策略需要决定目标服务副本和
当前请求路由。同一个策略会在五类运行状态的隐藏确定性变体上评测，未来 workload、
failure 和 link event 不可见。

## Observation

`decide(observation)` 接收 JSON-compatible 数据：

- 当前 timestep 和时段长度；
- 节点的 region、failure domain、CPU 容量和存活状态；
- 服务的单副本 CPU、服务率、基础延迟、P99 SLO、响应大小和可靠性等级；
- 当前各 region/service 的 demand，以及最多四个历史时段；
- active 和 pending replicas；
- region RTT 和当前跨区带宽上限；
- 上一步动作与粗粒度违规反馈。

Observation 不包含未来 trace，也不包含候选自行计算的得分分量。

## Action

必须准确返回：

```json
{
  "replicas": [
    {"service_id": "api", "node_id": "a-1", "count": 2}
  ],
  "routes": [
    {"service_id": "api", "source_region": "edge-a", "node_id": "a-1", "fraction": 0.8}
  ]
}
```

`replicas` 是完整的 desired placement。新副本 pending 一个时段后才 active；被移除的副本
立即停止服务。`routes` 只控制当前时段，且只能指向当前 active、同时被本动作保留的副本。
Fraction 合计可以小于 1，剩余请求会成为未服务流量并得到连续惩罚；合计大于 1 为非法。

## Hard-invalid 条件

- schema 错误、未知或重复 ID；
- bool 冒充 int、负数或非整数副本数；
- NaN/Infinity 或 `[0, 1]` 外的 route fraction；
- placement 超过物理 CPU，或放在故障节点；
- 向故障、pending、不存在或被本动作移除的副本路由；
- 每个 service/source 的 route sum 大于 1；
- import/runtime error、超时或响应大于 64 KiB。

高利用率、未完全路由、超载、SLA miss、临时故障影响、恢复慢和过度配置属于连续性能
后果，不直接判 invalid。

## Metrics 与评分

Evaluator 独立报告 request availability、request-weighted P95/P99、P99 SLO violation、
compute cost、cross-region GB/cost 和 failure recovery steps。

有效策略的每个 scenario 先得到 bounded engineering loss。当前 reliability + SLA 权重为
70%，其余由 latency、compute、bandwidth 和 recovery 构成；tail latency 按三个服务 P99
SLO 的中位数连续归一化；跨 scenario 的聚合为 75% 平均分 + 25% P20 分位数。

Raw metrics 始终可见，避免 combined score 隐藏工程权衡。Normalization、cap、极端策略
和权重敏感性分析见 `docs/scoring-calibration-report.md`。
