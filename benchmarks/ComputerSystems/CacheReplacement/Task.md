# CacheReplacement Task Specification

## 1. Background

### 1.1 The Engineering Problem

CPU caches are finite-capacity hardware structures. On every cache miss, the hardware must decide which existing line to evict to make room for the incoming line. This eviction decision — the **replacement policy** — directly determines cache hit rate and application performance.

- A 1% increase in LLC hit rate translates to 5–15% application speedup on modern CPUs
- Wrong eviction decisions cause cache pollution, thrashing, and severe performance degradation
- Engineers at Intel, AMD, ARM, and Apple have designed replacement policies for decades
- The problem remains open — no single policy dominates all workloads

### 1.2 Why LRU is the Baseline

LRU (Least Recently Used) is the classical replacement policy, used as the default baseline in virtually all replacement research (Cache Replacement Championship, Data Prefetching Championship, academic papers). It assumes temporal locality: recently accessed lines are likely to be accessed again soon.

**Returning LRU does not mean optimization is successful.** Score = 1.0 means parity; score > 1.0 means the agent discovered measurable improvement over a decades-old heuristic.

### 1.3 Competition Background

- **Cache Replacement Championship (CRC-2)**, ISCA 2017: https://crc2.ece.tamu.edu/
- **Data Prefetching Championship (DPC-3)**, ISCA 2019: https://dpc3.compas.cs.stonybrook.edu/
- Winners: SHIP (signature-based hit prediction), Hawkeye (optimal reference simulation)

### 1.4 Optimization Search Space

| Dimension | What the agent designs |
|---|---|
| **Metadata structure** | What per-line state to track (counters, signatures, reuse distance, history) |
| **Recency / frequency** | How to balance temporal vs access-frequency signals |
| **Victim selection** | Decision logic in `find_victim()` given current state |
| **Adaptivity** | Whether to detect workload phases and switch strategies |
| **State compression** | How to pack metadata within 64 KB budget |

---

## 2. Task Definition

The agent modifies `replacement/my_policy.cc` (within `// EVOLVE-BLOCK-START` / `// EVOLVE-BLOCK-END` markers) to implement a custom cache replacement policy. The evalutor performs 4 layers of validation and evaluation:

| Layer | Check | Outcome on failure |
|---|---|---|
| **L1: Source Validation** | Forbidden headers/APIs, randomness, dynamic memory, storage budget, EVOLVE-BLOCK integrity | `valid=0, score=0` |
| **L2: Compile** | Incremental build via ChampSim build system, timeout 300s | `valid=0, score=0` |
| **L3: Quick Verify** | Run on verify_trace.xz, check for crashes, timeout 120s | `valid=0, score=0` |
| **L4: Full Evaluation** | Run on 3 (quick) or 10 (full) SPEC traces, compute GMEAN score | Failed traces skipped |

### 2.1 Input

- `replacement/my_policy.h` — Class declaration (EVOLVE-BLOCK for member variables, read-only otherwise)
- `replacement/my_policy.cc` — Method implementations (EVOLVE-BLOCK for method bodies, read-only otherwise)

### 2.2 Output

The evaluator produces `metrics.json`:

```json
{
    "valid": true,
    "score": 1.15,
    "benchmark_version": "1.0.0",
    "mode": "full",
    "compile_time_s": 7.8,
    "simulation_time_s": 914.7,
    "num_traces_completed": 10,
    "num_traces_total": 10,
    "error": null
}
```

On failure:

```json
{
    "valid": false,
    "score": 0.0,
    "error": "Static validation: Forbidden header: <iostream>"
}
```

---

## 3. EVOLVE-BLOCK Contract

### 3.1 `replacement/my_policy.h` — Member Variable Declaration

The EVOLVE-BLOCK in the header file allows the agent to **add** member variables that store replacement policy metadata:

```cpp
// EVOLVE-BLOCK-START
// Agent may ADD member variables here (fixed-size arrays only):
//   uint8_t name[SIZE];
//   std::array<uint8_t, SIZE> name;
//
// Agent must NOT remove or modify existing base members:
//   long NUM_WAY, std::vector<uint64_t> last_used_cycles, uint64_t cycle
//
// Total EVOLVE-BLOCK storage ≤ 64 KB (checked by evaluator).
// EVOLVE-BLOCK-END
```

**Allowed**: fixed-size primitive arrays, `std::array<T,N>`
**Prohibited**: `std::vector`, `std::map`, dynamic containers, global/static variables

### 3.2 `replacement/my_policy.cc` — Method Implementation

The EVOLVE-BLOCK in the implementation file allows the agent to modify **three method bodies**:

```cpp
// EVOLVE-BLOCK-START
// Agent may modify method bodies below. Keep function signatures unchanged.

long my_policy::find_victim(uint32_t triggering_cpu, uint64_t instr_id,
                            long set, const champsim::cache_block* current_set,
                            champsim::address ip, champsim::address full_addr,
                            access_type type)
{
  // Return way index to evict: [0, NUM_WAY)
  // Default LRU: evict way with oldest last-use cycle
  auto begin = std::next(std::begin(last_used_cycles), set * NUM_WAY);
  auto end = std::next(begin, NUM_WAY);
  auto victim = std::min_element(begin, end);
  return static_cast<long>(std::distance(begin, victim));
}

void my_policy::replacement_cache_fill(uint32_t triggering_cpu, long set,
                                       long way, champsim::address full_addr,
                                       champsim::address ip,
                                       champsim::address victim_addr,
                                       access_type type)
{
  // Called when a new line is filled into the cache
  last_used_cycles.at(static_cast<std::size_t>(set * NUM_WAY + way)) = cycle++;
}

void my_policy::update_replacement_state(uint32_t triggering_cpu, long set,
                                         long way, champsim::address full_addr,
                                         champsim::address ip,
                                         champsim::address victim_addr,
                                         access_type type, uint8_t hit)
{
  // Called on every cache access. Update policy state.
  if (hit && access_type{type} != access_type::WRITE)
    last_used_cycles.at(static_cast<std::size_t>(set * NUM_WAY + way)) = cycle++;
}

// EVOLVE-BLOCK-END
```

### 3.3 Available Base Members

The following member variables are available for use in method implementations:

| Member | Type | Description |
|---|---|---|
| `NUM_WAY` | `long` | Cache associativity (number of ways per set) |
| `last_used_cycles` | `std::vector<uint64_t>` | Per-line last-use cycle timestamps (size = sets × ways) |
| `cycle` | `uint64_t` | Monotonically increasing cycle counter |

### 3.4 Forbidden (complete list)

| Category | Banned items |
|---|---|
| **Headers** | `<iostream>`, `<fstream>`, `<sstream>`, `<thread>`, `<mutex>`, `<future>`, `<shared_mutex>`, `<filesystem>`, `<unistd.h>`, `<fcntl.h>`, `<sys/stat.h>`, `<sys/mman.h>`, `<dlfcn.h>`, `<execinfo.h>`, `<signal.h>`, `<setjmp.h>` |
| **File I/O** | `fopen`, `fread`, `fwrite`, `fclose`, `open(`, `read(`, `write(`, `close(`, `mmap(`, `munmap(` |
| **System** | `system(`, `popen`, `fork` |
| **Threading** | `pthread_*`, `std::thread`, `std::async` |
| **Dynamic memory** | `new`, `delete`, `malloc(`, `free(`, `calloc(`, `realloc(` |
| **Dynamic containers** | `std::vector`, `std::map`, `std::unordered_map`, `std::set`, `std::list`, `std::deque` |
| **Non-determinism** | `rand()`, `srand(`, `random_device`, `mt19937`, `default_random_engine`, `time(`, `clock(` |
| **Exceptions** | `throw`, `try`, `catch` |
| **RTTI** | `dynamic_cast`, `typeid` |
| **Storage overflow** | Total declared arrays in header EVOLVE-BLOCK > 64 KB |
| **Interface violation** | Modifying function signatures, EVOLVE-BLOCK markers, or code outside EVOLVE-BLOCK |

---

## 4. Scoring

### 4.1 Formula

```
For each completed trace t:
  ratio[t] = IPC_candidate[t] / IPC_LRU[t]

final_score = exp( (1/N) * Σ ln(max(ratio[t], 0.001)) )
  where N = number of successfully completed traces
```

### 4.2 Interpretation

| Score | Meaning |
|---|---|
| 1.0 | Parity with LRU (baseline) |
| > 1.0 | Better than LRU |
| (0, 1.0) | Worse than LRU but functionally valid |
| 0 | Invalid (any layer failure) |

### 4.3 Edge Cases

| Scenario | Handling |
|---|---|
| Candidate IPC ≤ 0 | Trace skipped |
| Simulation crashes | Trace skipped |
| Per-trace timeout | Trace skipped |
| All traces skipped | `valid=0, score=0` |
| Baseline IPC ≤ 0 | `valid=0, error="Bad environment"` |

---

## 5. Evaluation Modes

### Quick Mode (`--mode quick`)

| Parameter | Value |
|---|---|
| Traces | `605.mcf_s-665B`, `625.x264_s-18B`, `607.cactuBSSN_s-2421B` |
| Warmup instructions | 10,000,000 |
| Simulation instructions | 20,000,000 |
| Expected runtime | ~15 minutes |
| Per-trace timeout | 600 seconds |
| Purpose | Agent iteration / rapid feedback |

### Full Mode (`--mode full`)

| Parameter | Value |
|---|---|
| Traces | 10 (all SPEC CPU 2017) |
| Warmup instructions | 50,000,000 |
| Simulation instructions | 100,000,000 |
| Expected runtime | 30–60 minutes |
| Per-trace timeout | 1800 seconds |
| Purpose | Leaderboard / final scoring |

---

## 6. Timeout Behavior

| Timeout type | Value | Effect |
|---|---|---|
| Compile | 300s | `valid=0, score=0` |
| Quick Verify | 120s | `valid=0, score=0` |
| Per-trace (Quick) | 600s | Trace skipped, remaining continue |
| Per-trace (Full) | 1800s | Trace skipped, remaining continue |

---

## 7. Baselines

### Official baseline: `baseline/lru.cc`

LRU (Least Recently Used). Score = 1.0. Used for computing IPC normalization.

### Sanity check: `baseline/random.cc`

Random replacement policy. Expected score < 1.0. **Not an official baseline.** Not included in leaderboard. Used to verify that the evaluator can distinguish policy quality:

```bash
# Expected: score < 1.0 (random is worse than LRU)
python verification/evaluator.py baseline/random.cc --mode quick
```

---

## 8. Examples

### Example: Well-formed policy (LRU)

This is the default implementation. It should produce `valid=1, score≈1.0`:

```cpp
long my_policy::find_victim(...) {
  auto begin = std::next(std::begin(last_used_cycles), set * NUM_WAY);
  auto end = std::next(begin, NUM_WAY);
  auto victim = std::min_element(begin, end);
  return static_cast<long>(std::distance(begin, victim));
}
```

### Example: Rejected (iostream)

```cpp
// EVOLVE-BLOCK-START
#include <iostream>  // ← Layer 1: Rejected. Forbidden header.
long my_policy::find_victim(...) { return 0; }
// EVOLVE-BLOCK-END
```

### Example: Rejected (rand)

```cpp
// EVOLVE-BLOCK-START
long my_policy::find_victim(...) {
  return rand() % NUM_WAY;  // ← Layer 1: Rejected. Non-deterministic.
}
// EVOLVE-BLOCK-END
```

### Example: Rejected (deepseek vector)

```cpp
// EVOLVE-BLOCK-START
std::vector<int> extra;  // ← Layer 1: Rejected. Dynamic container.
long my_policy::find_victim(...) { return 0; }
// EVOLVE-BLOCK-END
```

---

## 9. Usage

```bash
# Quick mode (agent iteration, ~15 min)
python verification/evaluator.py replacement/my_policy.cc --mode quick

# Full mode (final scoring, ~30-60 min)
python verification/evaluator.py replacement/my_policy.cc --mode full

# Validation tests
python verification/test_validation.py

# Frontier-Eng integration
python -m frontier_eval task=unified task.benchmark=ComputerSystems/CacheReplacement algorithm.iterations=0
```

---

## 10. Data Management

Traces are **ChampSim trace files generated from SPEC CPU 2017 workloads**, sourced from the [DPC-3 public repository](https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu/).

> ⚠️ **License notice**: This benchmark repository does **not** redistribute SPEC CPU traces. The repository only contains metadata, download instructions, and checksums. Users must download trace files from the original source via `bash data/download_traces.sh`.

### Trace specification

| Trace | Domain | Quick | Full | Compressed |
|---|---|---|---|---|
| `603.bwaves_s-3699B` | Float (scientific) | — | ✓ | ~50 MB |
| `605.mcf_s-665B` | Integer (combinatorial) | ✓ | ✓ | ~60 MB |
| `625.x264_s-18B` | Integer (video) | ✓ | ✓ | ~80 MB |
| `654.roms_s-842B` | Float (ocean) | — | ✓ | ~55 MB |
| `657.xz_s-3167B` | Integer (compression) | — | ✓ | ~70 MB |
| `600.perlbench_s-210B` | Integer (scripting) | — | ✓ | ~60 MB |
| `602.gcc_s-734B` | Integer (compiler) | — | ✓ | ~75 MB |
| `607.cactuBSSN_s-2421B` | Float (physics) | ✓ | ✓ | ~90 MB |
| `621.wrf_s-575B` | Float (weather) | — | ✓ | ~65 MB |
| `631.deepsjeng_s-928B` | Integer (AI/game) | — | ✓ | ~55 MB |

### Checksum verification

```bash
cd data/traces && sha256sum -c ../checksums.txt
```

---

## 11. References

- Cache Replacement Championship (CRC-2, ISCA 2017): https://crc2.ece.tamu.edu/
- Data Prefetching Championship (DPC-3, ISCA 2019): https://dpc3.compas.cs.stonybrook.edu/
- ChampSim simulator: https://github.com/ChampSim/ChampSim
- SPEC CPU 2017: https://www.spec.org/cpu2017/
- SRRIP/DRRIP: Jaleel et al., ISCA 2010
- SHIP: Wu et al., MICRO 2011
- Hawkeye: Jain and Lin, ASPLOS 2016
- TAGE-SC-L: Seznec, CBP 2016
- See `references/related_work.md` for full citations.
