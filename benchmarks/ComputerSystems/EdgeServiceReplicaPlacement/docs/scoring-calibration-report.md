# Scoring calibration report

## Verdict

The audit found two scoring defects and applied only the corresponding minimal fixes:

1. below-reference P99 differences were clipped to zero, making the tail-latency component
   inactive for every calibration policy;
2. compute and bandwidth losses stopped increasing at two budget units, which let a fixed
   full-capacity policy consume 13.95 cost units while receiving no penalty beyond 12.0.

No simulator, workload, scenario, metric, weight, or cross-scenario aggregation changed.
Raw metrics are therefore identical before and after; only normalized loss and score changed.

Reproduce the complete policy and sensitivity matrix with:

```text
python calibration/analyze_scoring.py --output scoring-analysis.json
```

## Scoring pipeline

```text
per-period demand, served traffic, latency, replicas, bandwidth, recovery
  -> scenario raw metrics
  -> component normalization and cap
  -> weighted scenario loss
  -> scenario score = 100 * exp(-loss)
  -> combined score = 0.75 * mean + 0.25 * P20 across 10 scenarios
```

| Component | Raw metric | Unit | Reference | Cap | Weight | Classification/rationale |
| --- | --- | --- | ---: | ---: | ---: | --- |
| reliability | unserved rate | ratio | 0.05 | 3 | 0.40 | benchmark operational target; same 5% threshold used for feedback |
| SLA | P99 SLO violation rate | ratio | 0.10 | 3 | 0.30 | synthetic calibration constant; service SLOs are checked before aggregation |
| tail latency | request-weighted P99 | ms | 180 | 2 | 0.10 | task-derived: median configured service P99 SLO (120/180/250 ms) |
| compute | active+pending replica cost | abstract cost/episode | 6.0 | 3 | 0.12 | baseline-calibrated synthetic budget |
| bandwidth | cross-region served volume | GB/episode | 1.0 | 3 | 0.04 | baseline-calibrated synthetic budget |
| recovery | periods until availability >= 0.99 | 5-minute periods | 6 | 2 | 0.04 | scenario-derived from the longest failure interval |

All physical units are normalized before addition. No component can dominate merely because
it is measured in milliseconds, gigabytes, or cost units.

## Tail-latency root cause

### Before

```text
excess = max(0, request_weighted_p99_ms / 180 ms - 1)
tail_component = min(2, excess / 0.50)
```

Observed P99 values were 28–66 ms for the relevant policies. Their raw P95/P99 values did
differ, the latency model responded to utilization/routing, and units were correct, but the
180 ms threshold clipped every value to exactly zero. This was a normalization/clipping bug,
not a congestion-model or unit bug.

### Change

```text
latency_reference_ms = median(service P99 SLOs) = 180 ms
tail_component = min(2, request_weighted_p99_ms / latency_reference_ms)
```

This preserves a small continuous incentive to improve latency while below an SLO. Actual
SLO breaches remain independently counted per service by the SLA component.

### Per-scenario evidence after the fix

Each policy cell is `P95/P99/tail_component`. Configured service P99 SLOs are API 120 ms,
search 180 ms, and media 250 ms.

| Scenario | Weak | Reasonable | Strong | Fixed full |
| --- | --- | --- | --- | --- |
| normal_diurnal-v0 | 35.3/40.9/0.2270 | 35.3/40.9/0.2270 | 35.2/40.6/0.2257 | 27.3/28.1/0.1563 |
| normal_diurnal-v1 | 35.8/41.7/0.2316 | 35.8/41.7/0.2316 | 34.9/40.2/0.2231 | 27.4/28.2/0.1569 |
| regional_burst-v17 | 48.2/61.4/0.3409 | 48.5/61.8/0.3433 | 38.3/45.6/0.2531 | 27.8/28.9/0.1607 |
| regional_burst-v18 | 38.4/45.7/0.2540 | 43.2/53.2/0.2958 | 36.2/42.3/0.2352 | 27.5/28.4/0.1579 |
| node_failure_burst-v34 | 50.9/65.6/0.3647 | 41.0/49.5/0.2747 | 40.8/49.2/0.2734 | 43.4/53.8/0.2990 |
| node_failure_burst-v35 | 44.0/54.7/0.3038 | 40.6/49.2/0.2733 | 39.5/47.4/0.2634 | 38.0/45.2/0.2509 |
| link_degradation-v51 | 35.5/41.2/0.2291 | 35.5/41.2/0.2291 | 35.2/40.7/0.2262 | 27.3/28.2/0.1566 |
| link_degradation-v52 | 36.1/42.2/0.2343 | 36.1/42.2/0.2343 | 35.0/40.4/0.2244 | 27.4/28.3/0.1572 |
| recovery_migration-v68 | 36.9/43.4/0.2410 | 40.5/48.9/0.2714 | 36.9/43.2/0.2398 | 29.7/31.9/0.1774 |
| recovery_migration-v69 | 35.5/41.2/0.2289 | 38.6/46.0/0.2554 | 37.6/44.4/0.2468 | 28.1/29.4/0.1634 |

## Compute/bandwidth cap root cause

### Before

Compute and bandwidth used a cap of 2.0. `fixed_full_capacity` and
`sla_first_overprovision` both cost 13.95 units, or 2.325 times the six-unit budget, but
were charged only 2.0. SLA-first consequently became the highest-scoring policy despite
occupying almost all node capacity throughout the episode.

### Change

The compute and bandwidth caps now use the evaluator's existing general cap of 3.0. This
keeps extreme loss bounded while preserving feedback through three budget units. Tail and
recovery retain cap 2.0 because no tested policy approaches those caps.

## Final four-policy component table

Values are mean per-scenario normalized component followed by weighted contribution.

| Policy | Reliability | SLA | Tail | Compute | Bandwidth | Recovery | Final score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| weak static | 0.1789 / 0.0716 | 0.3416 / 0.1025 | 0.2655 / 0.0266 | 0.7180 / 0.0862 | 0 / 0 | 0.0667 / 0.0027 | 74.0766 |
| reasonable | 0.1105 / 0.0442 | 0.2947 / 0.0884 | 0.2636 / 0.0264 | 0.7267 / 0.0872 | 0.9634 / 0.0385 | 0.0333 / 0.0013 | 73.9434 |
| strong | 0.1210 / 0.0484 | 0.1842 / 0.0553 | 0.2411 / 0.0241 | 0.7530 / 0.0904 | 1.0824 / 0.0433 | 0.0500 / 0.0020 | 74.4628 |
| fixed full | 0.0343 / 0.0137 | 0.1880 / 0.0564 | 0.1836 / 0.0184 | 2.3250 / 0.2790 | 0 / 0 | 0 / 0 | 70.2510 |

Normalization is applied per scenario before aggregation. Therefore `mean(raw)/reference`
can differ from the mean normalized component when individual scenarios hit a cap.

## Extreme-policy results

| Policy | Score | Availability | P99 ms | SLA violation | Compute | Cross-region GB | Recovery |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong | 74.4628 | 0.993951 | 43.401 | 0.018423 | 4.518 | 1.588 | 0.3 |
| weak static | 74.0766 | 0.991055 | 47.795 | 0.034160 | 4.308 | 0 | 0.4 |
| reasonable | 73.9434 | 0.994475 | 47.446 | 0.029475 | 4.360 | 1.168 | 0.2 |
| SLA-first overprovision | 73.1402 | 0.999708 | 29.998 | 0.005975 | 13.950 | 0 | 0 |
| fixed full capacity | 70.2510 | 0.998283 | 33.053 | 0.018799 | 13.950 | 0 | 0 |
| local routing only | 70.0369 | 0.981444 | 44.327 | 0.028112 | 4.319 | 0 | 0.4 |
| ignore failure | 62.1667 | 0.972494 | 46.029 | 0.046809 | 4.248 | 0 | 0.4 |
| zero | 11.7809 | 0 | 0 | 1.0 | 0 | 0 | 4.6 |
| cost-first underprovision | 11.1039 | 0.371147 | 52.538 | 0.638148 | 1.436 | 0 | 4.6 |
| minimum replica | 9.5307 | 0.483400 | 113.116 | 0.617490 | 1.436 | 16.401 | 4.6 |
| aggressive cross-region | 7.6351 | 0.172783 | 65.637 | 0.827217 | 13.950 | 24.929 | 4.6 |

No obvious extreme policy scores anomalously high after the cap fix. A zero-service policy
has a zero latency average because no requests are served, but reliability and SLA loss keep
its total score low; this does not provide an exploit.

## Weight sensitivity

Every major weight was independently tested at nominal -5%, -2%, nominal, +2%, and +5%.
The selected weight changes relatively; all other weights scale proportionally back to a
sum of one.

- `strong` remains the top policy in every relative perturbation.
- The ordering among strong, weak, reasonable, and SLA-first remains stable.
- Only two close low-ranked policies (`fixed_full_capacity` 70.2510 and
  `local_routing_only` 70.0369) swap under small compute/reliability changes. This is a
  legitimate engineering trade-off: one spends much more compute for availability, while
  the other accepts failures and uses no cross-region bandwidth.
- No relative perturbation produces a large score jump or elevates an obviously broken
  policy.

The separate absolute transfer `SLA -0.02, bandwidth +0.02` still changes the ordering of
weak/reasonable/strong. That is not numerical instability: it increases bandwidth's weight
by 50% and explicitly prefers the zero-cross-region weak policy. It should be described as
an engineering-preference change, not a two-percent relative perturbation.

## Before / change / after summary

| Item | Before | Root cause | Change | After |
| --- | --- | --- | --- | --- |
| tail signal | all calibration policies exactly 0 | below-180 values clipped | normalize P99 continuously by median configured SLO | nonzero 0.18–0.27 mean components; raw metrics unchanged |
| compute clipping | 13.95 cost normalized to 2.0 | cap below observed extreme | cap 3.0 | 13.95 normalizes to 2.325; full policies no longer win |
| bandwidth clipping | traffic above 2 GB/scenario free after cap | cap compressed remote-routing differences | cap 3.0 | more continuous penalty; aggressive remote policy remains low |
| calibration ranking | pre-correction scores (invalidated) | old normalization | no ranking-targeted tuning | strong 74.4628 > weak 74.0766 > reasonable 73.9434, reflecting explicit trade-offs |

The final ranking is not encoded as a required test. Tests require valid, deterministic,
distinct calibration policies rather than forcing a subjective preference ordering.
