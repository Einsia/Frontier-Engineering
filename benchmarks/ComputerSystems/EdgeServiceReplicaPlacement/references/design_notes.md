# Model scope and assumptions

This benchmark is a deterministic reduced-order control simulator, not a claim to
reproduce Kubernetes, a production data center, or a packet-level network.

- One period represents five minutes; the candidate acts for 24 periods.
- A desired scale-up becomes active one period later, representing aggregate cold-start
  and rollout delay. Scale-down is immediate.
- Each service replica has a fixed CPU footprint and nominal service rate. Queue pressure
  grows nonlinearly with utilization and affects reduced-order P95/P99 estimates.
- A route consumes response-size-weighted cross-region capacity. When a link or service
  is oversubscribed, requests are proportionally unserved rather than silently rerouted.
- Failed nodes immediately lose active and pending replicas. The candidate sees current
  failures but not future events.
- All workload and failure traces are synthesized before candidate execution from fixed
  seeds. Candidate behavior cannot alter the exogenous sequence.

The numerical values in `config.json` are calibration assumptions, not measured production
parameters. Their provenance and limitations are listed in
`docs/parameter_assumptions.md`.

Raw metrics are always emitted so score behavior remains auditable. Reliability plus SLA
loss carry 70% of the weight; latency, compute, bandwidth, and recovery account for the
remainder. See `docs/scoring-calibration-report.md` for normalization and exploit checks.
