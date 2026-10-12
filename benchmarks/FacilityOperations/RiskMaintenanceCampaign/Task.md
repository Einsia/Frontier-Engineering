# Risk-aware experimental-facility maintenance scheduling

Read both JSON campaign files under `environment/data/`. All inputs are public; there are no hidden additional instances.

Choose one integer start period for every operation in each campaign. Periods are 1-based. In `operations`, `tmax` is the last permitted start; `Delta[s-1]` is the contiguous duration for start s. `workload[pool][period][start]` gives the resource load, and `risk[period][start]` lists risk contributions for all scenarios in that period. Missing sparse contributions are zero. Numeric dictionary indexes are decimal strings. `capacity_pools` gives each pool's per-period `min` and `max` total load; satisfy both (official resource-comparison tolerance 1e-5). `calendar_groups` lists periods. Each entry in `incompatibilities` names two operations and a calendar group: the operations must not run simultaneously during that group's periods. Operations must respect the supplied last-start and duration/horizon data.

For each period t and scenario w, sum the scheduled operations' risk contributions to obtain R[t,w]. Let mean[t] be the mean across that period's scenarios. Sort those risks and select the value at 1-based index ceil(risk_quantile * scenarios_per_period[t]) as q[t]. The campaign objective is mean_risk_weight * mean_t(mean[t]) + (1-mean_risk_weight) * mean_t(max(0,q[t]-mean[t])). Minimize the SUM across the two campaigns. All risk values and resource coefficients are supplied. `reference_runtime_minutes` is historical metadata, not a solver stopping rule or constraint.

For each input filename, write the same filename under `the output directory supplied on the command line/`, containing `{"starts": {"operation-id": integer_start, ...}}`. Include every operation exactly once; duplicate JSON keys, unknown identifiers, missing operations and noninteger starts are rejected.


## Candidate interface and scoring

Edit only the EVOLVE-BLOCK in `scripts/init.py`. The evaluator invokes it as
`python scripts/init.py DATA_DIR OUTPUT_DIR ASSETS_DIR` in a fresh restricted
workspace. DATA_DIR contains the released input files, OUTPUT_DIR is writable,
and ASSETS_DIR supplies read-only baseline source/tools. Use input-derived
identifiers and regenerate outputs on every run; do not embed saved solutions.
Candidates can replace the algorithm completely within the editable block.

Every feasible result receives continuous `combined_score = -objective`; higher
is better. There is no hidden acceptance threshold. Invalid, missing, timed-out
or nonfinite results receive `valid=false` and `combined_score=-1e18`. The
evaluator independently recomputes feasibility and objective, ignoring candidate
score claims. The candidate has 900 seconds including compilation, 16 GiB
address-space limit, and no network or access to the verifier.
Use fixed seeds, stable tie-breaking and deterministic work budgets.
