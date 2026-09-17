# Multi-timestep tiny oracle

## Purpose

The tiny oracle checks the complete production state transition and score path on a case
small enough to enumerate. It is a validation fixture, not a new benchmark scenario and
not a baseline target.

It covers:

- desired placement;
- one-period cold start;
- pending-to-active transition;
- routing to active retained replicas;
- replica service capacity;
- latency and compute-cost accumulation;
- three timestep transitions;
- raw episode metrics, normalized loss components, and final score.

## Finite oracle case

- one service (`svc`);
- two one-replica nodes (`n1`, `n2`) in one region;
- three periods with demand rates `1, 3, 3` requests/second;
- `n1` initially active and `n2` absent;
- one replica per node maximum;
- route fractions on the declared finite grid `{0.0, 0.5, 1.0}`;
- no failures and no cross-region traffic.

“All feasible trajectories” means every hard-valid action sequence on this explicitly
declared finite grid. It does not mean every real-valued route fraction.

## Independence boundary

`verification/tiny_oracle.py` enumerates the trajectories and independently transcribes
the tiny state transition, metrics, and current scoring equation. It does not call
`EdgeServiceSimulator` during enumeration or metric calculation.

After choosing the best trajectory, the test passes exactly that action sequence through
the production `EdgeServiceSimulator` and production `scenario_score` via
`evaluate_action_sequence`. The test uses exact dictionary and floating-point equality;
there is no relaxed tolerance hiding a discrepancy.

## Executed result

Command:

```text
python verification/tiny_oracle.py
```

Enumerated trajectories: `723`

Best action sequence:

```json
[
  {
    "replicas": [
      {"service_id": "svc", "node_id": "n1", "count": 1},
      {"service_id": "svc", "node_id": "n2", "count": 1}
    ],
    "routes": [
      {"service_id": "svc", "source_region": "tiny", "node_id": "n1", "fraction": 1.0}
    ]
  },
  {
    "replicas": [
      {"service_id": "svc", "node_id": "n1", "count": 1},
      {"service_id": "svc", "node_id": "n2", "count": 1}
    ],
    "routes": [
      {"service_id": "svc", "source_region": "tiny", "node_id": "n1", "fraction": 0.5},
      {"service_id": "svc", "source_region": "tiny", "node_id": "n2", "fraction": 0.5}
    ]
  },
  {
    "replicas": [
      {"service_id": "svc", "node_id": "n1", "count": 1},
      {"service_id": "svc", "node_id": "n2", "count": 1}
    ],
    "routes": [
      {"service_id": "svc", "source_region": "tiny", "node_id": "n1", "fraction": 0.5},
      {"service_id": "svc", "source_region": "tiny", "node_id": "n2", "fraction": 0.5}
    ]
  }
]
```

Oracle raw metrics:

| Metric | Value |
| --- | ---: |
| request availability | 1.0 |
| unserved rate | 0.0 |
| request-weighted P95 | 32.0 ms |
| request-weighted P99 | 42.0 ms |
| P99 SLO violation rate | 0.0 |
| compute cost | 0.55 abstract cost units |
| cross-region traffic/cost | 0.0 |
| failure recovery steps | 0.0 |

Normalized components are zero except tail latency `42/180 = 0.23333333333333334` and
compute `0.55/6 = 0.09166666666666667`.

Oracle combined score: `96.62493678284117`

Production evaluator result: the raw metrics, all six normalized loss components, and
combined score were exactly equal. The covering test is
`test_bruteforce_oracle_matches_production_simulator_and_score_exactly`.

## Additional one-period dimensional check

The simulator suite also checks an analytical local-plus-cross-region routing case. With
150 requests/second split equally, local service can serve 75 requests/second. The remote
path is limited to:

```text
360 MB / (0.025 MB/request * 300 seconds) = 48 requests/second
```

The correct combined upper bound is therefore `75 + 48 = 123 requests/second`. This test
would fail if the simulator again compared a rate directly with a per-period volume.
