# Net3 Pump Scheduling

## Engineering problem and value

Drinking-water utilities must operate pumps while maintaining service pressure
and storage reserves. Pump operation consumes electricity, creates demand peaks,
and incurs mechanical wear when speeds change. This benchmark asks for a causal
closed-loop controller that balances those costs against hydraulic feasibility
under changing demand, tariffs, starting storage, and small leaks.

## Physical model

The evaluator uses the EPANET Net3 example network distributed with WNTR 1.4.0.
Each deterministic scenario uses one continuous 24-hour EPANET hydraulic
session with hourly control intervals and five-minute hydraulic steps; the
network and its tank state are not recreated between intervals.
The controller sets the speeds of pumps `10` and `335`; link `330` follows the
existing Net3 relationship with pump `335`. The evaluator removes the original
Net3 controls so that the submitted controller supplies the hourly actions.

## Editable program and input

Edit only the code between `EVOLVE-BLOCK-START` and `EVOLVE-BLOCK-END` in
`scripts/init.py`, preserving `control(observation)`. The controller receives one
JSON-compatible dictionary per hour containing only causal information:

| Field | Type | Meaning |
|---|---|---|
| `hour` | integer | Current interval, from 0 through 23 |
| `tank_levels_m` | mapping | Current pressure-head level in metres for tanks `1`, `2`, and `3` |
| `tariff` | number | Current hourly electricity-price coefficient |
| `demand_multiplier` | number | Current dimensionless network demand multiplier |
| `previous_action` | mapping | Previous speeds for pumps `10` and `335`; both are 0 initially |

The candidate runs in an isolated subprocess and may use only this observation
and state derived from earlier observations in the same scenario. It cannot read
the verifier, benchmark files, or hidden scenarios.

## Output

Return a dictionary with exactly the string keys `10` and `335`. Each value is a
finite pump-speed multiplier in the closed interval `[0, 1]`.

## Hard constraints

Every public and hidden scenario must:

- complete all 24 hydraulic intervals without controller, protocol, or EPANET
  failure;
- keep pressure at or above 20 m at every declared service node: `153`, `15`,
  `253`, `103`, `127`, `101`, `129`, `251`, `255`, and `105`;
- keep tanks `1`, `2`, and `3` within their Net3 minimum and maximum levels;
- finish each tank no more than 0.25 m below its scenario initial level.

Any failed scenario makes the complete candidate invalid and gives it zero
aggregate score.

## Objective and scoring

For each valid scenario the evaluator measures hourly energy cost, peak pump
power in kW, total speed switching, and terminal storage deficit in metres. Each
metric is compared with the frozen shipped baseline using
`baseline_metric / candidate_metric`, clipped to `[0, 1.5]`. The scenario score
is:

```text
100 * (0.55 * energy_ratio
     + 0.20 * peak_power_ratio
     + 0.10 * switching_ratio
     + 0.15 * terminal_recovery_ratio)
```

The six scenario scores aggregate as `0.70 * mean + 0.30 * worst_case`.
`score` therefore has a theoretical range of 0 to 150 and higher is better.
The unified `combined_score` is `score / 100`; the shipped baseline scores 1.0.
