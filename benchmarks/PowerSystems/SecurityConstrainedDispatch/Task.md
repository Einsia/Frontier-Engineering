# Task: Security-Constrained Dispatch

## Background

Power-system operators must dispatch generators economically while respecting
network physics and remaining feasible after credible component outages. A
dispatch that is cheap in the intact network may overload a transmission line,
violate voltage limits, or become infeasible after a line outage.

This benchmark uses three PGLib-OPF systems and twelve deterministic operating
scenarios. Scenarios combine normal operation, load variation, and selected N-1
line outages that were verified to admit AC-OPF solutions.

## Editable program

Edit only the logic between `EVOLVE-BLOCK-START` and `EVOLVE-BLOCK-END` in
`scripts/init.py`. Preserve:

```python
def solve(case: dict) -> dict:
    ...
```

The function is called once per scenario. It must return:

```python
{
    "pg_mw": [generator active-power setpoints],
    "vg_pu": [generator voltage-magnitude setpoints],
}
```

Both lists must contain exactly one finite value per generator, in the order
given by `case["generators"]`. All online generators at the same bus must use
the same voltage setpoint.

## Input

The `case` dictionary has the following exact top-level fields:

- `case_id: str`: PGLib system identifier.
- `scenario_id: str`: deterministic operating-scenario identifier.
- `base_mva: float`: system power base in MVA.
- `load_scale: float`: demand multiplier applied to the source case.
- `outage_branch: int | None`: zero-based source-case branch index removed in
  this scenario, or `None` for an intact network.
- `total_active_load_mw: float`: sum of active bus demand after scaling.
- `buses: list[dict]`: buses in MATPOWER row order.
- `generators: list[dict]`: generators in MATPOWER row order. Output arrays
  must use this same order.
- `branches: list[dict]`: branches in MATPOWER row order after applying the
  scenario outage.

Each entry in `case["buses"]` contains:

- `bus_id: int`, `type: int`;
- `pd_mw: float`, `qd_mvar: float`;
- `base_kv: float`;
- `vmin_pu: float`, `vmax_pu: float`.

Each entry in `case["generators"]` contains:

- `index: int`, `bus_id: int`, `online: bool`;
- `pmin_mw: float`, `pmax_mw: float`;
- `qmin_mvar: float`, `qmax_mvar: float`;
- `baseline_pg_mw: float`, `baseline_vg_pu: float`;
- `cost_model: list[float]`: the unmodified MATPOWER `gencost` row.

`cost_model` uses one of the MATPOWER encodings below. Polynomial rows are
`[2, startup, shutdown, n, c_(n-1), ..., c_0]`, representing coefficients in
descending power order. Piecewise-linear rows are
`[1, startup, shutdown, n, x_1, y_1, ..., x_n, y_n]`.

Each entry in `case["branches"]` contains:

- `index: int`, `from_bus: int`, `to_bus: int`;
- `resistance_pu: float`, `reactance_pu: float`, `charging_pu: float`;
- `rate_a_mva: float` (`0` means no active `RATE_A` limit);
- `tap_ratio: float`, `phase_shift_deg: float`;
- `in_service: bool`;
- `angle_min_deg: float`, `angle_max_deg: float`.

The baseline setpoints are feasible but deliberately non-optimal. They are a
starting point, not reference answers.

## Hard constraints

A candidate is valid only if every scenario satisfies all of the following:

1. AC Newton power flow converges.
2. Generator active and reactive powers remain within limits.
3. Bus voltage magnitudes remain within PGLib limits.
4. Apparent power at both ends of every rated in-service branch stays within
   `RATE_A`.
5. Branch angle differences remain within `ANGMIN` and `ANGMAX`.
6. Output is finite, has the exact required shape, and returns within two seconds
   per scenario.

Any hard violation makes the overall candidate invalid and sets
`combined_score` to zero.

## Scenarios

The benchmark evaluates three systems:

- IEEE RTS 24-bus;
- IEEE 57-bus;
- IEEE RTS 73-bus.

Each system has four scenarios:

- 98% load, intact network;
- 100% load, intact network;
- 100% load, selected line outage A;
- 102% load, selected line outage B.

The selected outages and fixed reference values are stored in the readonly
scenario manifest.

## Score

For each feasible scenario, three normalized components are computed:

```text
cost_efficiency = min(1.05, reference_AC_OPF_cost / candidate_cost)
thermal_margin  = clip((100 - max_branch_loading_percent) / 20, 0, 1)
voltage_margin  = 10th percentile normalized distance from voltage limits

scenario_score = 70 * cost_efficiency
               + 20 * thermal_margin
               + 10 * voltage_margin
```

The aggregate score emphasizes both average and worst-case behavior:

```text
combined_score = 0.75 * mean(scenario_score)
               + 0.25 * min(scenario_score)
```

Higher is better. The cost term rewards proximity to the frozen AC-OPF
references; the two margin terms reward dispatches that do not merely sit on
thermal or voltage limits. The cost component is capped to limit sensitivity to
numerical solver differences.

## Prohibited behavior

- Do not modify the evaluator, PGLib cases, scenario manifest, or metadata.
- Do not read or write files, launch subprocesses, access the network, or use
  wall-clock-dependent behavior from `solve`.
- Do not hard-code evaluator outputs or bypass AC power flow.
- Keep the policy deterministic.
