# Dependency-Aware Cybersecurity Patch Scheduling

This benchmark models offline patch selection and integer-slot scheduling under prerequisites, maintenance calendars, resource limits, asset exclusivity, service downtime limits, and rollback risk.

Each deterministic instance contains assets, services, renewable resources, vulnerabilities, and patches. A candidate returns a schedule containing selected patch identifiers and start slots. Omitted patches remain unapplied.

## Files

- `Task.md`: English candidate specification.
- `Task_zh-CN.md`: Simplified Chinese candidate specification.
- `scripts/init.py`: self-contained starter solver matching the baseline behavior.
- `verification/problem.py`: deterministic instance generation, baseline solvers, validation, and raw objective evaluation.

## Required API

`verification.problem` exposes:

- `generate_instances(seed) -> list[dict]`
- `solve_random(instance) -> dict`
- `solve_baseline(instance) -> dict`
- `solve_reference(instance) -> dict`
- `validate_solution(instance, solution) -> tuple[bool, str]`
- `evaluate_solution(instance, solution) -> int | float`

Every seed produces one small, one medium, and one large instance. Horizons, entity counts, dependency density, identifiers, and array order vary deterministically with the seed. Generation uses a local deterministic integer generator and does not invoke a solver.

## Objective

The raw metric is total expected monetary loss in microunits and is minimized. It combines:

1. Criticality-adjusted expected security loss accumulated before remediation.
2. Slot-specific business downtime loss for scheduled patches.
3. Expected rollback loss.

Probability products use integer parts-per-million arithmetic with round-half-up after each multiplication. The evaluator returns only the positive raw loss. Score normalization is performed by the benchmark framework using `log2(baseline / candidate)`.

## Baselines

The deterministic control solver returns the feasible empty schedule. The starter and baseline use dependency-aware benefit-density ordering, schedule complete prerequisite bundles at their earliest feasible slots, and retain only objective-improving bundles.

The reference solver exhaustively enumerates every dependency-closed patch subset and feasible start-time assignment on the five-patch small tier. Medium and large tiers use additional deterministic priority orders and forced-first lookahead schedules. The exact small-tier result audits solution quality, while the larger tiers preserve practical algorithmic headroom.

## Evidence

NIST SP 800-40 Rev. 4 motivates risk-based enterprise patch planning under operational constraints. CISA BOD 22-01 motivates prioritizing vulnerabilities with evidence of active exploitation and explicit remediation deadlines. The benchmark's monetary values and generated dependency graphs are synthetic calibration data, not empirical values attributed to either source.

## Scope

The model is reproducible and independently checkable, but it remains a planning abstraction. It does not model attacker adaptation, emergency approvals, uncertain durations, correlated rollback failures, partial deployments, undiscovered dependencies, incident response, or human coordination delays.

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## Evaluation Contract

The verifier recomputes `verifier_recomputed_total_expected_monetary_loss_microunits` and candidates must minimize it.
Each valid case is scored by `log2` improvement over the baseline and the final score is the
mean across cases. Invalid solutions receive `-1e18`.

## Evaluation Design

Setting: `offline_batch`. Arrival model: Each instance is a static planning batch: the complete vulnerability set, patch catalog, dependency graph, asset and service data, exploit-probability curves, capacities, maintenance windows, durations, and cost parameters are revealed before a schedule is submitted. No vulnerabilities, windows, or capacity changes arrive during execution. Benchmark instances are regenerated deterministically from fixed seeds, and the seed does not change in response to candidate behavior.

Objective rationale: Expected monetary loss is appropriate because patching is not valuable merely for maximizing patch count or minimizing completion time. It prices the security exposure retained by delaying or omitting patches while also charging for the business disruption and rollback exposure caused by applying them. Expressing all three components in a common monetary unit produces a continuous, auditable tradeoff and keeps feasibility rules separate from preferences. The raw objective is strictly lower-is-better and can be kept positive through instance construction, making it suitable for framework-owned log2_baseline_ratio normalization.

Literature alignment: NIST SP 800-40 Rev. 4 frames enterprise patching as risk-based preventive maintenance that must be planned alongside operational constraints. CISA BOD 22-01 provides a concrete basis for prioritizing vulnerabilities with evidence of active exploitation and for modeling remediation deadlines. This benchmark turns those planning principles into a deterministic offline optimization problem; its synthetic monetary loss, rollback, resource, and downtime parameters are benchmark abstractions rather than values claimed by either source. It differs from classical makespan scheduling by allowing economically rational patch omission and by jointly enforcing dependency closure, maintenance calendars, renewable resources, and service downtime limits.

Local execution is only for reviewed code:

```bash
python verification/evaluator.py scripts/init.py --local
```

Publish evaluation requires Docker and the pinned runtime image:

```bash
docker pull python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
python verification/evaluator.py scripts/init.py
```
<!-- BENCHGEN-PUBLIC-CONTRACT-END -->
