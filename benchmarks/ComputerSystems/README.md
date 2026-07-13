# Computer Systems

Includes computer-systems engineering optimization tasks:
- `MallocLab`: dynamic memory allocation.
- `DuckDBWorkloadOptimization`: analytical SQL workload tuning (index/materialized-view selection + query rewrite).
- `AdaptiveCompressedTelemetryExecution`: CPU-measured co-design of telemetry compression and compressed query execution.

`AdaptiveCompressedTelemetryExecution` is an execution-backed C++ task: candidate
codec and query code is compiled, correctness-checked, and timed on a pinned CPU.
It reports raw throughput and compression metrics as well as a storage/CPU economic
objective.

Note for contributors: ensure the evolved baseline source file contains `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END` markers (use `// ...` in C/C++).
