# SecurityConstrainedDispatch Restricted-Process Design

Date: 2026-07-13

## Scope

This change fixes only three contract violations confirmed during contribution review:

1. `vg_pu` is documented as required but is currently optional in the evaluator.
2. Candidate code can currently read task internals, access the network, and launch subprocesses despite explicit prohibitions.
3. Candidate module import has no infrastructure timeout and can prevent metrics from being written.

It does not add constraints that are absent from `Task.md`, `frontier_eval/constraints.txt`, or repository contribution requirements.

## Architecture

The trusted host evaluator retains scenario loading, AC power flow, hard-constraint checking, scoring, and metrics/artifact writing. Candidate import and `solve(case)` execute in a dedicated worker subprocess because the target server prohibits Linux namespaces and therefore cannot run Docker, Podman, or `unshare` isolation.

For every scenario, the evaluator serializes only the public `case` payload to JSON on standard input. The worker emits one JSON result on standard output. It starts in an empty temporary working directory and receives the candidate path plus public payload only; benchmark, verifier, and reference paths are not passed to candidate code.

The runner imports the candidate under an external wall-clock timeout, then installs a Python audit hook and Linux seccomp filter immediately before `solve()`. The audit hook rejects file-open, subprocess/process-launch, socket/network, dynamic-library loading, and equivalent audited operations. Seccomp independently denies filesystem-opening, process creation/execution, networking, tracing, namespace, mount, and other unnecessary system calls.

The worker runs with:

- an empty temporary current directory;
- sanitized environment variables;
- inherited standard input/output/error only;
- `no_new_privs` enabled before the seccomp filter;
- resource limits for address space, CPU time, output size, and open descriptors;
- a separate fixed ten-second infrastructure timeout for interpreter startup and candidate import;
- the contract-defined two-second wall-clock timeout for each `solve()` call, measured only after the audit and seccomp controls are installed;
- termination of the entire worker process group on timeout.

This design does not claim container-equivalent or mathematically absolute isolation. Without namespaces or a virtual machine, arbitrary native code cannot be made perfectly safe. The implementation must state this limitation accurately while enforcing every confirmed prohibited behavior with both application-level and kernel-level controls available on the server.

The host evaluator remains responsible for turning every candidate-side failure into numeric invalid metrics while returning exit code zero, as required by the unified runner contract.

## Candidate Runner Contract

The runner accepts:

- the candidate path supplied to the isolated worker;
- exactly one public scenario payload as JSON through standard input.

It imports the candidate under the separate ten-second infrastructure timeout, verifies that `solve` is callable, installs the restrictive audit hook and seccomp filter, then starts a fresh two-second budget and calls `solve()` once. Interpreter startup and import time never consume the `solve()` budget. It writes the returned object as JSON and does not read benchmark files or perform scoring. Import is allowed to load the candidate and ordinary Python dependencies. Prohibited behavior is blocked while `solve()` runs, which is the boundary stated in `Task.md`.

The host parser requires a dictionary containing both `pg_mw` and `vg_pu`. Each value must be a one-dimensional finite numeric list of exactly the generator count. Missing `vg_pu` is invalid; there is no fallback.

## Worker and Invocation

The benchmark adds an immutable candidate worker under `verification/`. The trusted evaluator invokes it with the same Python interpreter through `subprocess.Popen`, uses JSON pipes for communication, creates a new process group, sanitizes the environment, and applies the import infrastructure timeout. The worker enables `no_new_privs`, resource limits, the Python audit hook, and a seccomp allowlist/denylist before beginning the independent two-second `solve()` timeout.

The requirements file pins the selected Python seccomp binding. If seccomp is unavailable or filter installation fails, evaluation fails closed: the evaluator writes invalid numeric metrics and an actionable infrastructure failure rather than running the candidate without enforcement.

The unified task continues to call the trusted host evaluator through `frontier_eval/run_eval.sh`, so direct and unified evaluation enforce the same worker behavior.

## Error Handling

The following all produce `valid=0.0`, `combined_score=0.0`, and written `metrics.json` plus `artifacts.json`:

- candidate import exception;
- import-time or solve-time timeout;
- missing or non-callable `solve`;
- malformed JSON or extra non-JSON stdout;
- missing `pg_mw` or `vg_pu`;
- wrong output shape or non-finite values;
- worker launch, seccomp installation, or communication failure;
- any existing AC feasibility violation.

Failure artifacts identify the failure category without exposing reference answers or verifier internals.

## Documentation and Metadata

`README.md` and `README_zh-CN.md` will state the Linux/seccomp requirement, document dependency installation, explain the no-namespace security boundary, and retain exact direct and unified evaluation commands. Readonly metadata covers the candidate worker through the existing readonly `verification/` directory entry.

No API key, cache, or run output is committed.

## Verification

Automated negative tests will cover:

- missing `vg_pu`;
- wrong shape and non-finite output;
- file read and write attempts during `solve()`;
- subprocess attempts;
- network attempts;
- import-time infinite loop;
- solve-time infinite loop;
- candidate exceptions.

Positive verification will cover:

1. Seccomp capability and fail-closed check.
2. Direct baseline evaluation with the documented score.
3. Unified `algorithm.iterations=0` evaluation.
4. Strict readonly metadata audit, considering only requirements applicable to this benchmark.
5. A small authorized DeepSeek optimization run using the official OpenAI-compatible endpoint, `deepseek-v4-pro`, high reasoning effort, and enabled thinking.

The optimization run is evidence of end-to-end operability, not a claim of full reproducibility or optimization quality.

## Acceptance Criteria

- The released baseline remains valid and its score matches the documented value within normal floating-point tolerance.
- A candidate lacking `vg_pu` is invalid.
- Candidate `solve()` cannot open benchmark/reference/verifier files or access the network.
- Process-spawning attempts from `solve()` are rejected and cannot affect the host.
- Import hangs terminate within the separate ten-second infrastructure timeout; solve hangs terminate within the contract-defined two-second per-scenario budget. Both still produce numeric invalid metrics.
- Direct and unified baseline commands exit successfully and collect metrics/artifacts.
- The repository contains no secrets, absolute machine paths, caches, or transient outputs introduced by this change.
