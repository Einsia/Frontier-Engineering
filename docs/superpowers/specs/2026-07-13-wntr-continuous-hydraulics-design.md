# WNTR continuous-hydraulics evaluator design

## Goal

Replace the PumpScheduling evaluator's 24 independent one-hour Net3 simulations
with one continuous 24-hour EPANET hydraulic session per scenario. Preserve the
candidate interface, causal hourly control cadence, hard thresholds, and scoring
formula while making hydraulic state, tank dynamics, and pattern time continuous.

The task contract will explicitly define the pressure-constraint node set as
`153`, `15`, `253`, `103`, `127`, `101`, `129`, `251`, `255`, and `105`.

## Continuous simulation architecture

For each scenario, construct Net3 once, remove its original controls, set the
scenario's initial tank levels, configure the 24-hour duration and five-minute
hydraulic timestep, and schedule any leak on the same model. Open one EPANET
hydraulic session and retain it until the scenario ends.

At each integer hour from 0 through 23:

1. Read the current levels of tanks `1`, `2`, and `3` from the live hydraulic
   state.
2. Build the documented causal observation and call the candidate controller.
3. Validate the exact pump-key set and finite `[0, 1]` speeds.
4. Apply pump `10` and `335` speeds and open/closed states, plus the documented
   inverse state of link `330`.
5. Apply the scenario demand multiplier for that hour.
6. Advance the existing hydraulic session through that hour in five-minute
   steps without rebuilding or reopening the network.

The controller is called exactly 24 times. It cannot observe future tariffs,
demands, leaks, or hydraulic states.

## Metrics and constraints

At every hydraulic step, inspect pressure at all ten declared service nodes and
the bounds of all three tanks. Any convergence, protocol, pressure, or tank-bound
failure invalidates the scenario.

Compute pump power at every hydraulic step from nonnegative flow and delivered
head using the existing fixed efficiency. Integrate power over step duration to
obtain hourly energy, multiply each hour by its tariff, and retain the existing
hourly-average peak-power interpretation. Switching remains the sum of hourly
speed changes. Terminal deficit and terminal feasibility are computed from the
state at the end of the same continuous session.

The existing per-scenario ratio weights, clipping, six-scenario aggregation, and
`combined_score = score / 100` remain unchanged. The frozen baseline controller
and every candidate use the same continuous rollout function, so reference
metrics are regenerated during evaluation rather than carried over from the old
simulation method.

## Contract and public data

Update both Task documents to list the ten service-node IDs explicitly. Add the
same ordered set to a public reference file exposed through `agent_files.txt`.
Tests must compare that public declaration to the evaluator constant so the
contract and implementation cannot drift.

Update the README only where reproduction or runtime descriptions change. The
benchmark remains CPU-only, host-executed, deterministic, and based on WNTR
1.4.0 with no new external data.

## Error handling

Candidate load errors, invalid actions, timeouts, EPANET errors, non-finite
hydraulic values, and incomplete 24-hour runs produce an invalid scenario with
an actionable bounded error message. Evaluation still writes numeric `valid`,
`score`, and `combined_score` fields and exits successfully for candidate-caused
failures.

## Verification

Add tests that verify:

- one network construction and one hydraulic session per rollout;
- exactly 24 causal controller calls;
- continuous simulation time and five-minute state sampling;
- hourly action and demand-multiplier updates;
- leak activation over the documented absolute time window;
- pressure checks cover exactly the ten public service nodes;
- tank bounds and terminal constraints use the continuous final state;
- invalid candidate and hydraulic failures emit numeric invalid metrics;
- the baseline is feasible in all three public and three hidden scenarios.

Then run, in order:

1. task-local unit and contract tests;
2. direct baseline evaluation;
3. unified zero-iteration evaluation;
4. strict readonly metadata audit, interpreting unrelated repository failures
   separately;
5. one authorized DeepSeek V4 Flash OpenEvolve iteration.
