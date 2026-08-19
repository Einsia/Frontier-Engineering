# Task: BSM1 Aeration Control

## Engineering setting

Activated-sludge plants must remove carbon and nitrogen while limiting blower and pumping energy.
Influent flow and composition vary diurnally and become more difficult during rain and storm
events. This task exposes feedback control rather than a one-shot parameter fit: every 15 minutes,
the policy observes noisy process measurements and selects aeration and internal recycle settings.

## Process model and scenarios

The evaluator implements the standard BSM1 layout: five completely mixed ASM1 reactors (two
anoxic, three aerobic) followed by a ten-layer Takacs secondary settler. Fixed return-activated
sludge and waste-sludge flows are 18,446 and 385 m3/day. The plant is simulated for 14 days and
the final seven days are scored.

Three deterministic scenarios share the same diurnal base load:

- `dry`: diurnal and weekend load variation;
- `rain`: a sustained dilution-water event from day 8.35 to day 10.44;
- `storm`: two shorter hydraulic pulses centred near days 8.87 and 11.18.

The rain and storm series are deterministic IWA-derived engineering trajectories, not byte-for-byte
copies of the official BSM1 dynamic influent files. Sensor noise uses fixed, scenario-specific seeds.

## Observation

`control(observation)` receives only current or past information:

- `scenario_id`, `weather`, `time_day`, and `step_minutes`;
- influent flow and ammonium;
- dissolved oxygen in reactors 3, 4, and 5;
- nitrate in reactor 2;
- effluent ammonium and total nitrogen;
- `previous_action`.

The dissolved-oxygen, nitrate, and ammonium measurements contain deterministic sensor noise. The
policy does not receive future influent, process state arrays, random seeds, or evaluator internals.

## Action interface and hard constraints

Return exactly these four finite numeric fields:

```python
{
    "kla3_per_day": float,                    # [0, 360]
    "kla4_per_day": float,                    # [0, 360]
    "kla5_per_day": float,                    # [0, 360]
    "internal_recycle_m3_per_day": float,     # [0, 92230]
}
```

At one 15-minute step, each KLa may change by at most 120/day and internal recycle by at most
30,000 m3/day. Missing/extra fields, booleans, non-finite values, range errors, slew errors,
exceptions, protocol errors, or timeouts make the complete candidate invalid with score zero.
`reset_controller(scenario)` must reset all candidate-owned state before each scenario.

## Metrics and score

For every scored step, the evaluator computes the official BSM1 effluent quality index (EQI),
aeration energy, pumping energy, mixing energy, actuator switching, and normalized exceedance of
five standard limits: NH4-N 4, total nitrogen 18, COD 100, TSS 30, and BOD5 10 g/m3.

Each objective is mapped to a dimensionless utility:

```text
Uq = exp(-EQI / 6000)
Ua = exp(-aeration_energy / 5000)
Up = exp(-pumping_energy / 1200)
Um = exp(-mixing_energy / 600)
Us = exp(-4 * switching_index)

base = 100 * (0.45 Uq + 0.20 Ua + 0.10 Up + 0.10 Um + 0.15 Us)
scenario_score = base * exp(-6 * violation_index)
```

The aggregate rewards typical and worst-case behavior:

```text
combined_score = 0.75 * mean(scenario_scores) + 0.25 * min(scenario_scores)
```

The score is absolute and contains no frozen candidate baseline. A fixed published BSM1 operating
point is supplied only as editable starter code and as a reproducible comparison in the result log.

## Candidate process boundary

The evaluator copies the candidate to a temporary directory and imports it in a persistent worker.
Communication is JSON-only; import, each call, cumulative response time, and response size are
bounded. Candidate stdout is discarded and credentials are removed from its environment. This
prevents ordinary Python-level mutation of the parent evaluator; it is not a sandbox against
hostile native code or unrestricted filesystem/network access.
