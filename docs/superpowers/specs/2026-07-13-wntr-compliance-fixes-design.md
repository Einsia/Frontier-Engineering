# WNTR PumpScheduling Compliance Fixes

## Scope

Repair only the five confirmed submission blockers in
`WaterDistribution/PumpScheduling`: frozen-reference scoring, strict readonly
audit compatibility, unified-run documentation, causal-observation enforcement,
and explicit unified metric fields. No unrelated task constraints or refactors
are introduced.

## Scoring architecture

The shipped baseline controller will be copied to
`verification/baseline.py`. The evaluator will always load this readonly file
for reference rollouts and will load the submitted candidate only from the path
provided on the command line. Because `verification/` is readonly in unified
evaluation, replacing `scripts/init.py` can no longer replace the reference.

The evaluator will write numeric `valid`, `score`, and `combined_score` fields.
`score` remains the documented 0--150 task score. `combined_score` will be
`score / 100`, preserving the repository runner's current fallback semantics
while making the contract explicit. Invalid candidates receive zero.

## Causal controller isolation

Candidate source is copied to a temporary isolated directory and executed by a
persistent Python worker subprocess. The worker starts with an isolated Python
mode, a sanitized environment, a temporary working directory, and a restricted
import/open policy. It receives only JSON observations over standard input and
returns only JSON actions over standard output.

The evaluator retains the one-second call deadline, validates the exact pump
keys and finite speed bounds, and terminates the worker after each scenario.
Attempts to import task verifier modules, inspect benchmark files, or use paths
outside the isolated directory invalidate the rollout. Standard-library modules
needed for ordinary controller logic remain usable.

## Unified metadata and documentation

Add `frontier_eval/run_eval.sh` as the short benchmark-local wrapper expected by
the repository readonly audit. Add it to `readonly_files.txt`; the frozen
baseline is already covered by the existing `verification` entry.

Update the English README with:

- dependency installation;
- direct evaluator command;
- unified benchmark ID `WaterDistribution/PumpScheduling`;
- exact zero-iteration unified command;
- required Python runtime override;
- CPU, WNTR/EPANET, host-process, and trusted-evaluator assumptions.

Mirror operationally relevant commands in the optional Chinese README.

## Error handling

Candidate import errors, protocol violations, timeouts, prohibited file access,
invalid JSON, non-finite values, hydraulic failures, and constraint violations
produce an invalid scenario instead of crashing the evaluator. The evaluator
still writes `metrics.json` and `artifacts.json` and exits normally so the
unified runner can retain actionable diagnostics.

## Verification

Run, in order:

1. task unit tests, including scoring-reference separation and isolation tests;
2. direct baseline evaluator;
3. unified OpenEvolve baseline with zero iterations;
