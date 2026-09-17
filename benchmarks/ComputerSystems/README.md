# Computer Systems

Includes computer-systems engineering optimization tasks:
- `MallocLab`: dynamic memory allocation.
- `DuckDBWorkloadOptimization`: analytical SQL workload tuning (index/materialized-view selection + query rewrite).
- `CacheReplacement`: CPU cache replacement policy optimization. (Replaces the deleted `IndexOptimization`, which overlapped with `DuckDBWorkloadOptimization`.)

Note for contributors: ensure the evolved baseline source file contains `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END` markers (use `// ...` in C/C++).
