# WNTR Documentation and Audit Compliance

## Scope

Close the two remaining explicit contribution gaps for
`WaterDistribution/PumpScheduling`: complete task-contract documentation and
accurate readonly metadata. Do not add engineering constraints beyond the
existing task contract.

## Task contract documentation

Expand `Task.md` and its Chinese translation with only the repository-required
content:

- the operational pump-scheduling problem and its engineering/economic value;
- the WNTR 1.4.0 EPANET Net3 model and hourly closed-loop simulation;
- every causal observation field, type, meaning, and unit;
- the exact two-key pump-speed output contract;
- feasibility constraints already enforced by the evaluator;
- objective components, weights, reference normalization, clipping, and
  cross-scenario aggregation.

The documentation must match executable evaluator behavior exactly.

## Accurate evaluator entry points

Add real compatibility entry points rather than readonly declarations for
missing paths:

- `verification/evaluate.py` delegates to `verification/evaluator.py`;
- `frontier_eval/evaluate_submission.py` executes the same task-local evaluator
  contract as `frontier_eval/run_eval.sh`.

Do not create a `parse_mdriver_result.py` placeholder because MallocLab result
parsing is unrelated to this Python benchmark.

## Readonly audit correction

The repository audit currently treats four task-family-specific filenames as if
every unified benchmark must provide all four. Change the audit so required
coverage remains mandatory, while a recommended path is checked only when that
path exists in the benchmark. This preserves readonly protection without
forcing unrelated or nonexistent wrappers into metadata.

Remove nonexistent path declarations from the WNTR `readonly_files.txt` and
list the two real compatibility entry points explicitly. Existing directory
coverage remains intact.

## Tests and acceptance

Add tests that verify explicit numeric unified metrics, reference/candidate
separation, isolated file-access rejection, and both real wrappers. Run:

1. all WNTR unit and contract tests;
