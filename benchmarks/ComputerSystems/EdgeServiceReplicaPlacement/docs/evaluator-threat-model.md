# Evaluator threat model

## Scope

The evaluator treats candidate output as untrusted and independently computes placement,
routing, latency, availability, cost, recovery, and score. This review focuses on wrong
results, resource abuse, protocol failure, and reproducibility. It is not a claim that a
local Python subprocess is a hostile-code security sandbox.

## Attack surface review

| Attack surface | Current defense | Test covering it | Remaining limitation |
| --- | --- | --- | --- |
| `NaN` route fraction | Explicit numeric check plus `math.isfinite`; JSON RPC encoding also disables non-finite request values | `test_nan_route_is_rejected` | Candidate-internal non-finite state is irrelevant until it crosses the action boundary. |
| Positive/negative infinity | Same finite-number check; values cannot enter scoring | `test_extreme_route_float_is_rejected` | None known at the action boundary. |
| `bool` used as replica integer | Exact exclusion of `bool` before accepting `int` | `test_bool_cannot_impersonate_integer` | Python subclasses or unusual objects are removed by the JSON boundary. |
| Negative zero | `-0.0` route is accepted as numerically identical to `0.0`; replica counts must be integers and non-negative | Covered indirectly by finite/range validation; reviewed manually | Canonicalizing `-0.0` would not change simulator behavior or score, so no extra rejection was added. |
| Extreme finite route float | Range `[0,1]` enforced after finite conversion | `test_extreme_route_float_is_rejected`, `test_route_fraction_out_of_range_is_rejected` | None known. |
| Duplicate placement IDs | Exact `(service_id,node_id)` uniqueness | `test_duplicate_placement_is_rejected` | None known. |
| Duplicate route IDs | Exact `(service_id,source_region,node_id)` uniqueness | `test_duplicate_route_is_rejected` | Multiple different destination nodes are intentionally allowed. |
| Unknown service/node/region IDs | All IDs resolved against evaluator-owned config | `test_unknown_id_is_rejected`; malformed route test exercises nested validation | Config authenticity depends on the framework readonly boundary, not this check alone. |
| Missing top-level IDs/objects | Action must contain exactly `replicas` and `routes`; nested objects require exact field sets | `test_exact_top_level_schema_is_enforced`, `test_malformed_nested_route_is_rejected` | Omitting a service from desired placement is intentionally legal and means scale to zero; omitting routes is a poor but valid policy with continuous unserved-demand loss. |
| Unexpected keys | Exact key sets at top level and in each nested item | `test_exact_top_level_schema_is_enforced`, `test_malformed_nested_route_is_rejected` | This deliberately rejects forward-compatible extensions until the schema changes. |
| Negative/non-integer/huge replica count | Exact integer, non-negative range, then CPU-capacity check | `test_negative_and_noninteger_replica_counts_are_rejected`, `test_huge_replica_count_is_rejected_by_capacity` | Python arbitrary-size integer parsing occurs before capacity rejection, but the 64 KiB response limit bounds its textual size. |
| Over-capacity placement | Evaluator recomputes per-node CPU use from trusted service footprints | `test_capacity_is_checked` | CPU is a reduced abstract capacity, not a scheduler model. |
| Route fraction rounding | Per-key sum uses a documented `1e-8` tolerance | `test_route_sum_tolerance_has_a_strict_boundary` | The tolerance is an engineering choice and should be reviewed if the action schema changes. |
| Route sum slightly above one | Any sum above `1 + 1e-8` is invalid | `test_route_sum_above_one_is_rejected`, tolerance-boundary test | A sum within tolerance can serve at most a negligible excess before downstream capacity, and is accepted intentionally. |
| Route to pending replica | Route target must be active now and retained by desired placement | `test_pending_replica_cannot_receive_traffic` | Candidate receives pending state, so the behavior is diagnosable. |
| Route to failed node | Alive-node check applies to placement and routing | `test_failed_node_cannot_receive_placement`, `test_failed_node_cannot_receive_route` | The MVP models individual node failures only. |
| Route to a replica removed in the same action | Desired placement must retain a positive count in addition to current activity | Existing inactive-route path is exercised by simulator validation tests | A dedicated named regression test would be useful only if this branch later changes; current coverage is adequate. |
| Giant JSON/action | Worker response line capped at 64 KiB; action list capped at 256 total items | `test_oversized_response_is_rejected`; action-size path covered through schema validation | Reading is line-oriented; up to the cap must still be parsed. |
| Non-JSON stdout | Strict one-line JSON RPC; decoding/parsing failure closes worker | `test_non_json_result_is_rejected`, `test_non_json_stdout_cannot_corrupt_protocol` | Candidate must not use stdout for logging; stderr is the diagnostic channel. |
| Stderr spam | Stderr is continuously drained to avoid deadlock; retained tail bounded to 16 KiB | `test_stderr_spam_is_drained_and_tail_is_bounded` | Spam can consume CPU/I/O until timeout; this is reliability control, not a byte-level OS quota. |
| Candidate exception | Worker returns typed error; evaluator fails closed and scores invalid candidate as zero | `test_candidate_exception_is_reported`, `test_invalid_action_cannot_compete` | Error text is diagnostic only and is not trusted as a metric. |
| Infinite loop | Per-call and per-scenario monotonic deadlines; process tree termination | `test_infinite_loop_times_out` | Terminating descendants is best-effort and platform-dependent without a container/job-object sandbox. |
| Abrupt process exit / nonzero exit | EOF and process status become a candidate error; remaining scenarios are not silently scored | `test_abrupt_process_exit_is_reported` | Native crashes provide only bounded stderr diagnostics. |
| Missing `decide` entry point | Candidate import/reset handshake fails closed | `test_missing_decide_fails_closed` | None known. |
| Malformed nested objects | Exact dict/list/field/type checks before simulation | `test_malformed_nested_route_is_rejected` and other schema tests | Deep nesting is bounded indirectly by response bytes; Python JSON decoder depth remains an implementation limit. |
| Candidate mutates observation | Observation crosses a JSON serialization boundary; evaluator retains its own objects | `test_candidate_mutates_only_its_json_copy_of_observation` | Candidate can mutate its private copy, which is harmless and intentional. |
| Candidate self-reports score or metrics | Unexpected output keys fail schema; evaluator computes every raw metric and score itself | `test_exact_top_level_schema_is_enforced`, `test_invalid_action_cannot_compete` | Candidate code can know the public formula, as expected for an optimization benchmark. |
| Candidate changes exogenous randomness | All workload/failure/link traces are generated from fixed seeds before candidate execution | `test_generation_is_deterministic` | Fixed public scenario structure can be overfit; only one of two variants per family is included in feedback artifacts. |
| Nondeterministic replay | Official baselines are compared across repeated evaluator runs | `test_reasonable_baseline_is_deterministic`; final validation repeats the reasonable baseline three times | An arbitrary candidate is not automatically run three times or rejected for nondeterminism. |
| Worker modifies copied candidate or temp working directory | Candidate runs from an isolated temporary copy and clean working directory | `test_reasonable_candidate_round_trip` exercises the boundary | This protects evaluator reliability, not host files outside the temp directory. |
| Worker reads/writes host files or opens network connections | No evaluator-level claim or defense | Not applicable | **Unmitigated at OS level.** A plain Python worker can attempt filesystem, process, or network operations allowed to the host account. A stronger sandbox would require framework/container/OS controls and maintainer agreement. |
| Evaluator/reference mutation in unified execution | Task metadata declares verifier/config/docs/runtime files readonly and copies a controlled set | Metadata/readonly audit; direct tests do not model framework mounts | Readonly effectiveness belongs to Frontier Eval execution. Running the evaluator directly does not create a readonly filesystem. |

## Isolation boundaries

### Process reliability isolation

The runtime copies the candidate to a temporary working directory, launches a separate
isolated-mode Python process, speaks bounded JSON-lines RPC, drains stderr, imposes
timeouts, and terminates the process tree on failure. These controls prevent common hangs,
stdout corruption, shared-object mutation, and unbounded retained diagnostics.

### Framework readonly boundary

The unified metadata lists evaluator, simulator, runtime, worker, configuration, tests,
docs, and wrapper files as readonly. Frontier Eval is responsible for applying that
boundary in a unified run. It is distinct from candidate-process isolation and must be
checked with the repository audit plus an actual zero-iteration unified run.

### OS-level sandboxing

There is no benchmark-owned OS security sandbox. The subprocess is not proof against host
filesystem access, network access, subprocess creation, environment discovery, or every
resource-exhaustion technique. No Docker/Kubernetes layer was added in this review because
that would change scope and should follow maintainer guidance.

## Review conclusion

No new high-score exploit was found after adding targeted tests for extreme values,
malformed objects, route-tolerance boundaries, failed-node routing, abrupt exit, stdout
noise, stderr spam, and observation mutation. The most important remaining limitation is
the absence of OS-level hostile-code containment; documentation now states that explicitly.
