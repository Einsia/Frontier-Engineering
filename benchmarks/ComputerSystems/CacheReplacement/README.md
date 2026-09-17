# CacheReplacement — CPU Cache Replacement Policy Optimization

An AI agent designs a CPU cache replacement policy by modifying C++ code. The policy is compiled into the [ChampSim](https://github.com/ChampSim/ChampSim) simulator and evaluated on SPEC CPU 2017 memory access traces. The agent's goal is to outperform the classic LRU baseline.

| Quick Links | |
|---|---|
| Task specification | [Task.md](Task.md) / [Task_zh-CN.md](Task_zh-CN.md) |
| Engineering domain | Computer Architecture — microarchitectural optimization |
| Existing benchmarks comparison | MallocLab (OS), DuckDB (Database) → **CacheReplacement (Architecture)** |
| Competition background | [Cache Replacement Championship (CRC-2, ISCA 2017)](https://crc2.ece.tamu.edu/) |

---

## Architecture Pipeline

```
  Agent edits replacement/my_policy.cc (within EVOLVE-BLOCK markers)
                          │
                          ▼
  ┌──────────────────────────────────────────────────────┐
  │ Layer 1: Source Validation                           │
  │  · Best-effort static scan                           │
  │  · Forbidden headers: <iostream>, <fstream>, <thread>│
  │  · Forbidden APIs: fopen, mmap, system, fork         │
  │  · No randomness: rand(), mt19937, time()            │
  │  · No dynamic memory: new, delete, malloc, free      │
  │  · Storage budget ≤ 64 KB (approximate check)        │
  │  · EVOLVE-BLOCK integrity check                      │
  │  FAIL → valid=0, score=0                             │
  └──────────────────────┬───────────────────────────────┘
                         │ PASS
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │ Layer 2: Compile into ChampSim                       │
  │  · config.sh + make -j4 (incremental build)          │
  │  · Environment: g++-13, C++17, -O3 -fno-exceptions   │
  │  · Timeout: 300s                                     │
  │  FAIL → valid=0, score=0                             │
  └──────────────────────┬───────────────────────────────┘
                         │ PASS
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │ Layer 3: Quick Verify                                │
  │  · Run on verify_trace.xz (10M warmup + 20M sim)     │
  │  · Checks: no crash, valid IPC value                 │
  │  · Purpose: fast rejection of broken policies        │
  │  · NOT used for scoring                              │
  │  · Timeout: 120s                                     │
  │  FAIL → valid=0, score=0                             │
  └──────────────────────┬───────────────────────────────┘
                         │ PASS
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │ Layer 4: Full Evaluation                             │
  │  · Quick mode: 3 traces, ~15 min                     │
  │  · Full mode: 10 traces, ~30-60 min                  │
  │  · Per-trace: 50M warmup + 100M simulation           │
  │  · IPC extracted from ChampSim stdout                │
  │  · score = GMEAN(IPC_candidate / IPC_LRU)            │
  │  · Failed traces are skipped (remaining continue)    │
  └──────────────────────┬───────────────────────────────┘
                         │
                         ▼
              Output: {valid, score, per_trace, error}
```

---

## Scoring

```
score = geometric_mean( IPC_candidate[t] / IPC_LRU[t] ) over all completed traces t

  score = 1.0    → parity with LRU baseline
  score > 1.0    → better than LRU
  score ∈ (0,1)  → worse than LRU but functionally valid
  score = 0      → invalid (safety/compile/runtime failure)
```

Baseline LRU vs LRU always gives score = 1.0. Score > 1.0 means the agent discovered measurable improvement over a decades-old heuristic.

### Metrics output (metrics.json)

```json
{
    "valid": true,
    "score": 1.15,
    "benchmark_version": "1.0.0",
    "mode": "full",
    "compile_time_s": 7.8,
    "simulation_time_s": 914.7,
    "num_traces_completed": 10,
    "error": null
}
```

### On failure

```json
{
    "valid": false,
    "score": 0.0,
    "error": "Static validation: Forbidden header: <iostream>"
}
```

---

## Evaluation Modes

| Mode | Traces | Warmup | Simulation | Expected runtime | Use case |
|---|---|---|---|---|---|
| **Quick** (`--mode quick`) | 3 (mcf, x264, cactuBSSN) | 10M | 20M | ~15 min | Agent iteration |
| **Full** (`--mode full`) | All 10 | 50M | 100M | ~30-60 min | Final scoring |

---

## File Structure

```
CacheReplacement/
├── replacement/
│   ├── my_policy.h          # Class declaration (EVOLVE-BLOCK for member vars)
│   └── my_policy.cc         # Method implementation (EVOLVE-BLOCK for methods) ← Agent target
├── verification/
│   ├── evaluator.py         # 4-layer evaluation pipeline
│   ├── test_validation.py   # 10 Layer-1 validation tests
│   ├── Dockerfile           # Ubuntu 22.04, gcc-13, cmake 3.22
│   └── requirements.txt     # pyyaml
├── baseline/
│   ├── lru.cc               # LRU reference (official baseline)
│   ├── random.cc            # Random policy (sanity check only, score < 1.0)
│   ├── metrics.json         # Local test results
│   └── result_log.txt       # Test environment & results
├── frontier_eval/           # Frontier-Eng integration metadata
├── references/
│   ├── constants.json       # Parameter definitions
│   ├── problem_config.json  # Trace lists, timeout config
│   ├── generated_baseline.json  # Auto-generated LRU IPC cache
│   └── related_work.md      # Academic references
└── data/                    # Auto-downloaded (NOT in git)
    ├── download_traces.sh   # Automated download script
    ├── checksums.txt        # SHA256 checksums
    ├── traces/              # 10 SPEC CPU 2017 .xz traces
    └── ChampSim/            # Simulator source (commit 51588e1d)
```

---

## EVOLVE-BLOCK Contract Summary

The agent modifies **two files**, each with `// EVOLVE-BLOCK-START` / `// EVOLVE-BLOCK-END` markers:

### `replacement/my_policy.h` — Member variables (within EVOLVE-BLOCK)

```cpp
// EVOLVE-BLOCK-START
// Agent may add fixed-size arrays here:
uint8_t   history_table[1024];      // 1 KB
uint16_t  access_counters[64];      // 128 bytes
// Total ≤ 64 KB (checked by evaluator)
// EVOLVE-BLOCK-END
```

### `replacement/my_policy.cc` — Method implementations (within EVOLVE-BLOCK)

```cpp
// EVOLVE-BLOCK-START
// Agent may modify:
//   - find_victim() body        → eviction decision logic
//   - replacement_cache_fill()  → fill handler
//   - update_replacement_state() → state update
//
// Agent must NOT modify:
//   - function signatures
//   - code outside EVOLVE-BLOCK
// EVOLVE-BLOCK-END
```

### Forbidden (causes immediate rejection with valid=0)

| Category | Examples | Detection |
|---|---|---|
| **Headers** | `<iostream>`, `<fstream>`, `<thread>`, `<mutex>`, `<filesystem>`, `<unistd.h>`, `<fcntl.h>` | Header scan |
| **File I/O** | `fopen`, `fread`, `fwrite`, `open(`, `read(`, `write(`, `mmap(`, `munmap(` | API scan |
| **System** | `system(`, `popen`, `fork` | API scan |
| **Threading** | `pthread_`, `std::thread`, `std::async` | API scan |
| **Dynamic memory** | `new`, `delete`, `malloc(`, `free(`, `calloc(`, `realloc(` | Regex scan |
| **Dynamic containers** | `std::vector`, `std::map`, `std::unordered_map`, `std::set`, `std::list`, `std::deque` | Container scan |
| **Non-determinism** | `rand()`, `srand(`, `random_device`, `mt19937`, `time(`, `clock(` | Function scan |
| **Exceptions/RTTI** | `throw`, `try`, `catch`, `dynamic_cast`, `typeid` | Keyword scan |
| **Storage overflow** | Total declared arrays > 64 KB | Static size sum |
| **Interface violation** | Missing EVOLVE-BLOCK markers, modified read-only code | Diff check |

---

## Setup

### Prerequisites

- **Python 3.10+**
- **C++17 capable compiler** (g++-12+ or clang)
- **CMake ≥ 3.22**
- **~10 GB free disk space** (for trace download + ChampSim build)

### Step-by-step

```bash
# 1. Clone ChampSim simulator
git clone https://github.com/ChampSim/ChampSim.git data/ChampSim
cd data/ChampSim
git checkout 51588e1d6f97875fe8de1a3621d28668bff83fcf
git submodule update --init
./vcpkg/bootstrap-vcpkg.sh
./vcpkg/vcpkg install
cd ../..

# 2. Download SPEC CPU 2017 traces
bash data/download_traces.sh

# 3. Install Python dependencies
pip install -r verification/requirements.txt

# 4. Run baseline test (quick mode)
python verification/evaluator.py replacement/my_policy.cc --mode quick
```

### Docker

```bash
docker build -t champsim-eval -f verification/Dockerfile .
docker run --rm -v $(pwd):/benchmark champsim-eval
```

---

## Validation Tests

```bash
python verification/test_validation.py
```

Expected output: all 10 tests pass:

```
  [PASS] 1. Normal LRU policy: clean
  [PASS] 2. Forbidden header <iostream>: Forbidden header: <iostream>
  [PASS] 3. rand() usage: Non-deterministic function: rand()
  [PASS] 4. fopen() file I/O: Forbidden API: fopen
  [PASS] 5. std::vector in EVOLVE-BLOCK: Dynamic container: std::vector
  [PASS] 6. new operator: Dynamic memory: ...
  [PASS] 7. mt19937 randomness: Non-deterministic function: mt19937
  [PASS] 8. system() call: Forbidden API: system(
  [PASS] 9. Missing EVOLVE-BLOCK-END: Missing '// EVOLVE-BLOCK-END' in .cc file
  [PASS] 10. Budget exceeded: Storage budget exceeded: ~100000 B > 65536 B
```

---

## Integration with Frontier-Eng

```bash
python -m frontier_eval task=unified task.benchmark=ComputerSystems/CacheReplacement algorithm.iterations=0
```

---

## Differences from existing ComputerSystems benchmarks

| Benchmark | Engineering domain | Agent's task | Language |
|---|---|---|---|
| `MallocLab` | OS / Memory management | Implement malloc/free/realloc | C |
| `DuckDBWorkloadOptimization` | Database / Query optimization | Select indexes + rewrite SQL | Python |
| **`CacheReplacement`** | **Computer architecture** | **Design CPU cache eviction policy** | **C++** |

---

## References

- Cache Replacement Championship (CRC-2, ISCA 2017): https://crc2.ece.tamu.edu/
- Data Prefetching Championship (DPC-3, ISCA 2019): https://dpc3.compas.cs.stonybrook.edu/
- ChampSim simulator: https://github.com/ChampSim/ChampSim
- SPEC CPU 2017 traces: https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu/
- Related work: [references/related_work.md](references/related_work.md)
