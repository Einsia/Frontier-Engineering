# Task: Dynamic edge service replica placement and routing

Improve the policy inside the EVOLVE-BLOCK in `scripts/init.py`. At each five-minute
period, choose desired service replicas and current request routes. The same policy is
evaluated across hidden deterministic variants of five operating regimes. Future workload,
failure, and link events are not visible.

## Observation

`decide(observation)` receives JSON-compatible data containing:

- timestep and period duration;
- nodes with region, failure domain, CPU capacity, and current alive status;
- services with CPU/replica, service rate, base latency, P99 SLO, response size, and
  reliability class;
- current regional service demand and up to four historical periods;
- active and pending replicas;
- region RTTs and current cross-region bandwidth limits;
- the prior action and coarse violation feedback.

No future trace values or candidate-computed score components are supplied.

## Action

Return exactly:

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

`replicas` is the complete desired placement for the next state. New replicas are pending
for one period. Removed replicas stop serving immediately. `routes` controls only the
current period and may target active replicas that the same action retains. Fractions may
sum to less than one; the remainder becomes unserved demand and receives a continuous
performance penalty. Fractions above one are invalid.

## Hard-invalid conditions

- malformed schema, unknown or duplicate IDs;
- booleans used as integers, negative/non-integer replica counts;
- NaN/Infinity or route fractions outside `[0, 1]`;
- placement above physical CPU capacity or on failed nodes;
- routing to failed, pending, absent, or immediately removed replicas;
- per-service/source route sum above one;
- import/runtime error, timeout, or response above 64 KiB.

Utilization, under-routing, oversubscription, SLA misses, cross-region traffic, temporary
failure impact, slow recovery, and overprovisioning remain continuous performance effects.

## Metrics and score

The evaluator independently reports request availability, request-weighted P95/P99,
P99-SLO violation rate, compute cost, cross-region GB/cost, and failure recovery steps.
For valid policies, each scenario receives a bounded engineering loss. Reliability and SLA
components carry 70% of the current weight; latency, compute, bandwidth, and recovery form
the remainder. Tail latency is normalized continuously by the median configured service
P99 SLO. The aggregate is 75% mean scenario score plus 25% 20th-percentile score.

Raw metrics remain visible so engineering trade-offs are not hidden by the combined score.
Normalization, caps, extreme-policy checks, and weight sensitivity are documented in
`docs/scoring-calibration-report.md`.
