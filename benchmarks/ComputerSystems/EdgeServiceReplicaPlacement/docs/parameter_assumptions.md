# Parameter provenance and assumptions

## Status and interpretation

This document inventories the parameters that materially affect the MVP result. It is
not evidence that the current numbers describe a particular cloud provider or production
deployment. Unless a row explicitly says otherwise, values are local MVP assumptions
chosen to exercise the state transitions and engineering trade-offs.

The provenance labels used in this document are:

- `source-backed`: supported by a cited external source;
- `engineering simplification`: a deliberately reduced model or implementation guardrail;
- `scenario-derived budget`: derived from an explicit scenario duration or bound;
- `baseline-calibrated`: scaled against measured policies in this benchmark;
- `synthetic calibration parameter`: selected to produce auditable deterministic scenarios;
- `arbitrary placeholder requiring maintainer feedback`: provisional value whose suitability
  should be discussed before a formal PR.

There are currently **no numerical values claimed as source-backed**. Values without a
formal source are identified below as a **synthetic calibration assumption for the MVP**,
not presented as measured industry data.

## Topology, time, and service model

| Parameter | Current value/range | Unit | Used where | Type | Rationale/source |
| --- | ---: | --- | --- | --- | --- |
| Control period | 5 | minutes | `config.json`; observation; link-volume conversion | arbitrary placeholder requiring maintainer feedback | A short aggregate control interval that makes cold start and recovery visible without creating a large simulation. It is not a measured autoscaler interval. |
| Episode length | 24 | periods (120 minutes) | `make_scenario` | engineering simplification | Long enough to contain a baseline, event, and recovery phase while keeping CPU evaluation fast. |
| Regions | 3 | logical regions | `config.json` | engineering simplification | Minimum small topology that permits local, adjacent, and higher-latency routing choices. Region names are synthetic. |
| Nodes per region | 2 (6 total) | logical nodes | `config.json` | engineering simplification | Two failure domains per region permit a placement-diversity decision without modeling a cluster. |
| Failure domains | one rack label per node | logical label | node observations and placement reasoning | engineering simplification | Exposes correlated-placement structure; the MVP currently fails individual nodes, not entire racks. |
| Node CPU capacity | 10.0 | abstract CPU-capacity units/node | placement validation | synthetic calibration parameter | Synthetic calibration assumption for the MVP. Combined with per-replica footprints, it forces multi-service capacity choices but is not a vCPU claim. |
| API CPU footprint | 2.0 | CPU-capacity units/replica | placement validation | synthetic calibration parameter | Synthetic calibration assumption for the MVP; separates replica count from service throughput. |
| Search CPU footprint | 2.5 | CPU-capacity units/replica | placement validation | synthetic calibration parameter | Synthetic calibration assumption for the MVP; search is intentionally the largest footprint. |
| Media CPU footprint | 1.5 | CPU-capacity units/replica | placement validation | synthetic calibration parameter | Synthetic calibration assumption for the MVP; no claim about a real media service. |
| API nominal service rate | 90.0 | requests/second/active replica | service-capacity scaling | synthetic calibration parameter | Synthetic calibration assumption for the MVP. It leaves normal-load headroom but makes burst handling consequential. |
| Search nominal service rate | 65.0 | requests/second/active replica | service-capacity scaling | synthetic calibration parameter | Same role as API rate, with a lower synthetic throughput. |
| Media nominal service rate | 50.0 | requests/second/active replica | service-capacity scaling | synthetic calibration parameter | Same role as API rate, with a lower synthetic throughput. |
| Scale-up delay | 1 | control period (5 minutes) | `pending` to `active` transition | engineering simplification | Represents aggregate scheduling, startup, and readiness delay. It is explicitly not a measured container-start time. Scale-down is immediate in the MVP. |
| Bootstrap placement | 1 replica/service/region, round-robin over two nodes | replicas | simulator initialization | engineering simplification | Avoids a meaningless all-cold first period and provides a deterministic initial state. |

## Workload, event, and network assumptions

| Parameter | Current value/range | Unit | Used where | Type | Rationale/source |
| --- | ---: | --- | --- | --- | --- |
| Base request rate | API 54; search 34; media 25 | requests/second/region before modifiers | `_base_demand` | synthetic calibration parameter | Synthetic calibration assumption for the MVP. Values are sized against nominal service rates to create both spare capacity and overload regimes. |
| Region demand factors | 1.08, 0.94, 0.82 | multiplier | `_base_demand` | synthetic calibration parameter | Creates asymmetric regions so uniform placement is not automatically optimal. |
| Diurnal factor | 0.82 to 1.12 | multiplier | `_base_demand` | synthetic calibration parameter | A deterministic sinusoid supplies gradual demand change. It is not fitted to a production trace. |
| Per-scenario variant factor | 0.96 to 1.04 | multiplier | `make_scenario` | synthetic calibration parameter | Seeded variation prevents two variants from being byte-identical while keeping comparisons controlled. |
| Regional burst | API/search 1.85; media 1.55, steps 8–12 | multiplier for 5 periods (25 minutes) | regional-burst scenarios | synthetic calibration parameter | Creates a short overload that rewards headroom and timely scale-up. It is not an empirical burst distribution. |
| Recovery-migration load increase | 1.45, steps 7–14 | multiplier for 8 periods (40 minutes) | recovery-migration scenarios | synthetic calibration parameter | Makes post-failure restoration and later scale-down observable. |
| Node-failure duration | steps 8–13 | 6 periods (30 minutes) | node-failure-burst scenarios | synthetic calibration parameter | Long enough for a delayed replacement to become useful; not a production MTTR claim. |
| Recovery-migration failure duration | steps 6–10 | 5 periods (25 minutes) | recovery-migration scenarios | synthetic calibration parameter | Separates failure onset, recovery start, and workload normalization in a small episode. |
| Local RTT | 7, 8, 9 | milliseconds | latency model | synthetic calibration parameter | Gives a small local-path difference. Values are illustrative, not measured. |
| Cross-region RTT | 32, 35, 54 | milliseconds | latency model | synthetic calibration parameter | Creates near/far routing choices without modeling geography. Values are illustrative, not provider claims. |
| Cross-region capacity | 360 | megabytes/link/control period | link-capacity scaling | synthetic calibration parameter | Synthetic calibration assumption for the MVP. With a five-minute period this equals 1.2 MB/s (9.6 Mb/s), intentionally tight enough to expose routing trade-offs. |
| Link-degradation factor | 0.22, steps 9–15 | multiplier (79.2 MB/period) | link-degradation scenarios | synthetic calibration parameter | Creates a deterministic capacity incident on both directions of one region pair. |
| API response size | 0.025 | megabytes/request | link load and cross-region volume | synthetic calibration parameter | Synthetic calibration assumption for the MVP; only relative traffic size is intended. |
| Search response size | 0.04 | megabytes/request | link load and cross-region volume | synthetic calibration parameter | Synthetic calibration assumption for the MVP; only relative traffic size is intended. |
| Media response size | 0.18 | megabytes/request | link load and cross-region volume | synthetic calibration parameter | Makes media routing more bandwidth-sensitive. It is not a measured object-size distribution. |
| Scenario seeds | `4100 + 17*family_index + variant` | integer seed | scenario generation | engineering simplification | Fixed seeds make replay deterministic. All exogenous traces are generated before candidate execution. |
| Variants per family | 2; variant 0 exposes feedback, variant 1 is validation-only | scenarios | `SCENARIOS` and public artifacts | engineering simplification | Small MVP split supports review of generalization plumbing; ten scenarios are not enough to claim broad external validity. |

## Latency, reliability, and cost semantics

| Parameter | Current value/range | Unit | Used where | Type | Rationale/source |
| --- | ---: | --- | --- | --- | --- |
| Base service latency | API 12; search 20; media 28 | milliseconds | P95/P99 reduced-order model | synthetic calibration parameter | Synthetic calibration assumption for the MVP; represents service time before queue-pressure adjustment. |
| Queue-pressure function | `u^2 / max(0.08, 1-u)`; input utilization first capped at 0.995 for latency | dimensionless | P95/P99 calculation | synthetic calibration parameter | Smooth monotone penalty that becomes steep near saturation. It is a calibration curve, not a fitted queueing model. |
| Capacity utilization cap | incoming/capacity capped at 1.25; latency input capped at 0.995 | dimensionless | service scaling and latency | engineering simplification | Keeps overload state representable and prevents a singular/infinite latency value. |
| Tail multipliers | P95 0.85; P99 1.35 | dimensionless | latency model | synthetic calibration parameter | Separates P95 and P99 continuously. These are not empirical percentiles. |
| P99 SLO thresholds | API 120; search 180; media 250 | milliseconds | served-request SLO violation count | arbitrary placeholder requiring maintainer feedback | Provisional service-specific thresholds chosen to create differentiated tolerance. They are not contractual SLAs. |
| Unserved request semantics | requested rate not served by route, link, or replica capacity | requests/second aggregated by equal periods | availability and SLO violation | engineering simplification | Unserved demand counts as an SLO violation; the simulator never silently reroutes omitted/overflow traffic. |
| Availability | total served rate / total demand rate over equal-length periods | ratio | raw metric, reliability loss, recovery | engineering simplification | Equal period lengths make summing rates equivalent to request-weighted aggregation over the episode. |
| Recovery threshold | first post-recovery period with availability at least 0.99 | periods | `failure_recovery_steps` | arbitrary placeholder requiring maintainer feedback | A simple observable recovery definition. It does not model a multi-window reliability objective. |
| Compute price | 0.02 | abstract cost units/active-replica-period | compute cost | arbitrary placeholder requiring maintainer feedback | A relative cost coefficient only; it is not USD or a provider price. |
| Pending-replica price factor | 0.5 | multiplier | compute cost during cold start | arbitrary placeholder requiring maintainer feedback | Represents partial resource consumption before readiness. |
| Cross-region price | 0.08 | abstract cost units/gigabyte | cross-region cost | arbitrary placeholder requiring maintainer feedback | A relative coefficient only; it must not be described as a cloud-provider tariff. |
| Decimal GB conversion | 1024 MB/GB in current code | MB/GB conversion | cross-region cost | engineering simplification | The implementation uses 1024 for consistency with its current configuration; terminology should be clarified before merge. |

## Validation and runtime guardrails

| Parameter | Current value/range | Unit | Used where | Type | Rationale/source |
| --- | ---: | --- | --- | --- | --- |
| Route-sum tolerance | `1e-8` | fraction | hard route validation | engineering simplification | Allows harmless floating-point accumulation but rejects a sum more than `1 + 1e-8`. |
| Capacity tolerance | `1e-9` | CPU-capacity units | hard placement validation | engineering simplification | Avoids rejecting a mathematically equal sum due only to floating-point representation. |
| Maximum action items | 256 | placement plus route records/action | hard action validation | engineering simplification | Bounds parsing and per-step work well above the legitimate MVP action space. |
| Maximum response line | 64 KiB | bytes/RPC response | policy runtime | engineering simplification | Prevents unbounded candidate output; it is a reliability guardrail, not a security sandbox. |
| Retained stderr tail | 16 KiB | bytes | policy runtime diagnostics | engineering simplification | Keeps useful error context while bounding retained memory. The worker still consumes I/O until termination. |
| Startup timeout | 3.0 | seconds/scenario worker | evaluator/runtime | engineering simplification | Current CPU reliability budget; must be calibrated if dependencies or host assumptions change. |
| Decision timeout | 0.35 | seconds/call | evaluator/runtime | arbitrary placeholder requiring maintainer feedback | Current MVP limit chosen above baseline latency. It is not a repository-wide requirement. |
| Scenario total timeout | 12.0 | seconds/worker | evaluator/runtime | engineering simplification | Bounds candidate runtime over 24 decisions. The project-level personal goal remains an approximately 60-second full evaluation. |

## Provisional scoring parameters

| Parameter | Current value/range | Unit | Used where | Type | Rationale/source |
| --- | ---: | --- | --- | --- | --- |
| Reliability/SLA/tail/compute/bandwidth/recovery weights | 0.40 / 0.30 / 0.10 / 0.12 / 0.04 / 0.04 | share of normalized loss | `scenario_score` | arbitrary placeholder requiring maintainer feedback | Reliability plus SLA deliberately total 70%; exact weights remain provisional pending calibration/review. |
| Unserved-rate budget | 0.05 | ratio | reliability normalization | engineering simplification | Matches the benchmark's 5% availability-feedback threshold; not an external SLA. |
| SLO-violation budget | 0.10 | ratio | SLA normalization | arbitrary placeholder requiring maintainer feedback | Sets a scale for continuous loss; not an official SLA. |
| P99 latency reference | 180 | milliseconds | continuous tail-latency normalization | scenario-derived budget | Median of the three configured service P99 SLOs (120/180/250 ms); raw per-service SLO checks remain separate. |
| Compute budget | 6.0 | abstract cost units/episode | compute normalization | baseline-calibrated | Sized around current policies; no external economic interpretation. |
| Cross-region-volume budget | 1.0 | gigabytes/episode | bandwidth normalization | baseline-calibrated | Sized to make cross-region use visible after correct rate-to-volume conversion. |
| Recovery budget | 6.0 | periods | recovery normalization | scenario-derived budget | Matches the longest synthetic node-failure duration, not a real recovery target. |
| Per-component caps | 3.0 for reliability/SLA/compute/bandwidth; 2.0 for tail/recovery | normalized-loss units | `scenario_score` | engineering simplification | Bounds extreme loss while retaining observed compute/bandwidth differences; the earlier 2.0 compute/bandwidth cap was removed after an overprovision exploit test. |
| Score mapping | `100 * exp(-weighted_loss)` | score points | `scenario_score` | arbitrary placeholder requiring maintainer feedback | Monotone positive mapping. Raw metrics remain authoritative; formula is not frozen. |
| Cross-scenario aggregation | 75% mean + 25% P20 | score points | `evaluate` | arbitrary placeholder requiring maintainer feedback | Gives some weight to weak scenarios without making the single worst seed dominate. |

## Dimensional consistency audit

- Workload and service capacity are rates in requests/second. Fractions and capacity
  scaling operate on rates.
- Cross-region link limits are volumes in megabytes/control period. A routed rate is
  converted with `requests/second * MB/request * period_minutes * 60 seconds` before it
  is compared with the link limit. Served cross-region volume uses the same conversion.
- A previous MVP implementation omitted the period-seconds multiplier. The implementation
  and the analytical one-period oracle test now use the same dimensionally correct
  conversion; the correction materially narrowed the baseline score gap and is disclosed
  in the calibration report.
- Latency values are all milliseconds. The queue-pressure term and tail multipliers are
  dimensionless.
- Compute and bandwidth prices are deliberately abstract cost units. They are never added
  directly to milliseconds or ratios: each score component is normalized first.
- Because every simulated period has equal duration, episode availability and violation
  rates can aggregate per-period request rates without changing the resulting ratio.

## Maintainer decisions still needed

1. Whether the five-minute control interval and one-period aggregate cold start are a
   useful reduced-order abstraction.
2. Whether any workload, RTT, service-rate, response-size, failure-duration, or SLO value
   needs a cited public source before formal submission.
3. Whether abstract cost units are acceptable or should be replaced by an explicitly
   sourced economic model.
4. Whether the provisional score budgets, weights, and P20 aggregation provide appropriate
   optimization pressure after stronger baseline calibration.
