# Microgrid Battery Dispatch

## Background

Commercial microgrids with rooftop solar and battery storage can reduce
electricity cost by shifting energy away from expensive hours, absorbing local
solar surplus, and limiting monthly peak demand. A practical controller must
respect battery limits, round-trip losses, and degradation cost while reacting to
load, solar, and tariff forecasts.

## Objective

Write a deterministic battery dispatch policy that minimizes operating cost over
several fixed microgrid cases. Each case contains hourly load, PV generation,
buy/sell tariff, demand charge, battery capacity, charge/discharge limits, and
efficiency values.

## Candidate API

The evaluator imports `dispatch_action(state)` from `scripts/init.py`.

`state` contains:

- `case_id`, `t`, `hour`
- `soc_kwh`, `min_soc_kwh`, `capacity_kwh`
- `max_charge_kw`, `max_discharge_kw`
- `charge_efficiency`, `discharge_efficiency`
- `load_forecast_kw`, `pv_forecast_kw`
- `buy_price_forecast`, `sell_price_forecast`
- `demand_charge_per_kw`
- `degradation_cost_per_kwh`

The function returns a single finite float:

- positive: discharge kW
- negative: charge kW
- zero: idle

The simulation timestep is one hour.

## Constraints

- Do not import external packages.
- Do not read or write files.
- Keep the public `dispatch_action(state)` interface.
- Keep all editable logic inside the EVOLVE block.
- The policy must be deterministic for the same input state.

## Scoring

For each case the evaluator simulates the dispatch policy and computes:

```text
total_cost =
  grid_import_cost
  - export_credit
  + demand_charge
  + battery_degradation_cost
  + infeasible_action_penalty
```

`combined_score = -mean(total_cost across cases)`, so higher is better.
Feasible policies receive `valid = 1.0`; non-finite actions or evaluator errors
receive an invalid score.
