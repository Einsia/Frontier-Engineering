# Adaptive Link Scheduling

## Background

Wireless base stations continually decide which users receive resource blocks,
what modulation and coding scheme (MCS) to use, and how much power to transmit.
Good schedulers exploit favorable channel states while protecting users with
urgent queues and respecting power budgets. These decisions directly affect
throughput, latency, energy use, and fairness.

## Objective

For each fixed frame snapshot, produce one scheduling decision per resource
block. The verifier simulates packet delivery using deterministic SNR thresholds
and scores weighted throughput minus outage, power, budget, and fairness costs.

## Candidate API

The evaluator imports `schedule_frame(frame)` from `scripts/init.py`.

`frame` contains:

- `frame_id`
- `num_resource_blocks`
- `mcs_table`: list of `{mcs, snr_threshold_db, bits_per_rb}`
- `power_min_dbm`, `power_max_dbm`, `power_budget_mw`
- `users`: each user has `id`, `queue_bits`, `latency_weight`,
  `min_service_bits`, and `snr_estimate_db` per resource block

Return a list with `num_resource_blocks` entries. Each entry should be a mapping
with `user`, `mcs`, and `power_dbm`.

## Constraints

- Do not import external packages.
- Do not read or write files.
- Keep the public `schedule_frame(frame)` interface.
- Keep all editable logic inside the EVOLVE block.
- The scheduler must be deterministic for the same input frame.

## Scoring

For each resource block, the evaluator computes:

```text
effective_snr = snr_estimate_db + (power_dbm - 20)
```

The selected MCS succeeds if `effective_snr` reaches the MCS threshold plus a
small implementation margin. Successful transmissions deliver `bits_per_rb`
subject to the selected user's remaining queue. Failed transmissions consume
power and incur outage penalty.

The frame utility combines latency-weighted delivered bits, minimum-service
satisfaction, Jain fairness, power cost, and budget violations.

`combined_score = mean(frame_utility across frames)`, so higher is better.
