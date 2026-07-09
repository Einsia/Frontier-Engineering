# Clock-Aware FPGA Placement — Benchmark Design Report

> **Status**: Design Phase (pre-implementation)  
> **Target**: Frontier-Engineering `benchmarks/FPGA/ClockAwarePlacement/`  
> **Baseline**: aug-elfPlace (DREAMPlaceFPGA)  
> **Reference Data**: ISPD'2016 FPGA Contest Benchmarks + FPGA-example1

---

## Table of Contents

1. [Repository Investigation Notes](#1-repository-investigation-notes)
2. [Baseline Investigation Notes](#2-baseline-investigation-notes)
3. [Benchmark Architecture Design](#3-benchmark-architecture-design)
4. [Evaluation Design](#4-evaluation-design)
5. [Task.md Outline](#5-taskmd-outline)
6. [Risk Review](#6-risk-review)
7. [Implementation Roadmap](#7-implementation-roadmap)

---

## 1. Repository Investigation Notes

### 1.1 Existing benchmarks studied

| Benchmark | Domain | Pattern | Notes |
|-----------|--------|---------|-------|
| TopologyOptimization | StructuralOptimization | Unified | Cleanest example of unified pattern |
| HighReliableSimulation | WirelessChannelSimulation | Unified | Has runtime/ directory for shared modules |
| DiffSimThermalControl | AdditiveManufacturing | Unified | Uses verification/evaluator.py directly |
| MannedLunarLanding | Astrodynamics | Custom (legacy) | Has eval/ dir, own evaluator code |

### 1.2 Common patterns (Unified task)

#### Directory layout mandate:
Every task MUST have: `Task.md`, `README.md`, `references/`, `verification/`, `scripts/`, `frontier_eval/`.
`baseline/` is OPTIONAL but recommended.

#### frontier_eval/ metadata files (each a single text file):

| File | Purpose | Typical content |
|------|---------|----------------|
| initial_program.txt | Editable entry point path | scripts/init.py |
| eval_command.txt | How to invoke evaluation | {python} frontier_eval/run_eval.py --candidate {candidate} --metrics-out metrics.json --artifacts-out artifacts.json |
| eval_cwd.txt | Working directory for eval | . |
| agent_files.txt | Files shown to the agent | README.md, Task.md, scripts/init.py, frontier_eval/constraints.txt |
| readonly_files.txt | Non-editable files | references, verification, runtime, frontier_eval, README.md, Task.md |
| constraints.txt | Task-specific rules for agent | UnifiedTask template + task-specific bullets |
| copy_files.txt | Files to copy into candidate workspace | . |
| candidate_destination.txt | Where to place candidate | scripts/init.py |
| artifact_files.txt | Output files to collect | Usually empty (handled by framework) |

Two evaluator wrapper variants:

1. **With wrapper** (TopologyOptimization, HighReliableSimulation):
   - frontier_eval/evaluator.py — thin wrapper that loads verification/evaluator.py
   - frontier_eval/run_eval.py — CLI runner that imports evaluator.py and calls evaluate()
   - eval_command.txt = {python} frontier_eval/run_eval.py ...

2. **Direct** (DiffSimThermalControl):
   - No frontier_eval/evaluator.py or run_eval.py
   - eval_command.txt = {python} verification/evaluator.py {candidate} ...

#### verification/evaluator.py interface:

```python
def evaluate(program_path: str, *, repo_root: Path | None = None) -> dict:
    \"\"\"
    Full evaluation pipeline
    \"\"\"
    metrics = {
        "combined_score": INVALID_COMBINED_SCORE,  # -1e18
        "valid": 0.0,
        "runtime_s": 0.0,
    }
    # ... scoring logic ...
    return _wrap(metrics, artifacts)
```

#### Scoring conventions:
- combined_score is always the primary optimization target (higher = better)
- valid is 1.0 if all hard gates pass, 0.0 otherwise
- Invalid solutions get combined_score = -1e18
- For minimization problems: combined_score = -raw_metric
- Results wrapped via _wrap() using openevolve.evaluation_result.EvaluationResult

#### EVOLVE-BLOCK convention:
```python
# EVOLVE-BLOCK-START
\"\"\"
Task Name — Description
- ALLOWED TO MODIFY: <specific functions>
- NOT ALLOWED TO MODIFY: <interface functions>
\"\"\"
import ...

# — DATA LOADING (NOT ALLOWED TO MODIFY) —
def load_input(): ...

# — OPTIMIZATION ALGORITHM (ALLOWED TO MODIFY) —
def optimize(...): ...

# — OUTPUT (NOT ALLOWED TO MODIFY) —
def main():
    # output format must match evaluator expectations
    ...

if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
```

### 1.3 README.md conventions

```
# <Task Name>

One-paragraph summary. Then File Structure, Quick Start, Run with frontier_eval.
```

### 1.4 Task.md conventions

```
# <Task Name>

## 1. Problem
## 2. Design Variables / Input
## 3. Physical Model / Background
## 4. Objective
## 5. Constraints
## 6. Submission Format / Output
## 7. Scoring
```

## 2. Baseline Investigation Notes

### 2.1 aug-elfPlace pipeline

```
Benchmark files (.nodes/.nets/.pl/.scl/.lib/.lc)
        |
        v
    PlaceDBFPGA.read()          <- C++ parser (place_io)
        |
        v
    NonLinearPlaceFPGA.__call__()
        |
        |-- Global placement (Nesterov accelerated gradient descent)
        |   |-- 3-level nested: L_gamma -> L_lambda -> L_sub
        |   |-- Objective: wirelength + sum density_weight[r] * density_penalty[r]
        |   |-- gamma controls wirelength smoothness
        |   |-- lambda (density_weight) controls density penalty strength
        |   |-- Overflow tracking -> stopping criteria
        |
        |-- DSP/RAM legalization (auction-based, runs during GP)
        |
        |-- LUT/FF packer-legalization (runs after GP)
        |
        +-- Output: .pl file (name x y z [/FIXED])
```

### 2.2 Key files and their roles

| File | Role | Editable by agent? |
|------|------|--------------------|
| dreamplacefpga/Placer.py | Entry point | No - boilerplate |
| dreamplacefpga/Params.py | Configuration loader | Seed - agent provides param values |
| dreamplacefpga/PlaceDB.py | Database + I/O | No - infrastructure |
| dreamplacefpga/NonLinearPlace.py | Placement engine | Partial - the optimization loop |
| dreamplacefpga/PlaceObj.py | Objective function | Partial - the objective terms |
| dreamplacefpga/BasicPlace.py | Base class | No - infrastructure |
| dreamplacefpga/EvalMetrics.py | Metric tracking | No - used by evaluator |
| dreamplacefpga/ops/place_io/ | File parser | No - infrastructure |

### 2.3 Configurable parameters

**Optimization hyper-parameters** (candidates for evolution):
- global_place_stages: multi-stage configs (bins, iterations, learning_rate)
- density_weight: initial density penalty weight
- target_density: target density per region
- stop_overflow: stopping criterion
- gamma: wirelength smoothing parameter
- RePlAce_ref_hpwl: reference HPWL for density weight update
- gp_noise_ratio: initial noise for perturbation

**Architecture parameters** (fixed by benchmark):
- scl_file, net_file, nodes_file etc. - file paths
- num_bins_x, num_bins_y - density grid resolution

### 2.4 Output format

```
<instance_name> <x> <y> <z> [/FIXED]
inst_0 42 15 0
inst_2 103 0 25 FIXED
```

- Movable instances: name x y z (no suffix)
- Fixed instances: name x y z /FIXED
- z encodes site position within a column (for FPGA sites)

## 3. Benchmark Architecture Design

### 3.1 Design Alternatives

#### Alternative A: Full pipeline compilation
- **What agent does**: Modifies scripts/init.py with full placer source code (optimization loop, objective)
- **Evaluation**: Compile C++ ops -> run placement -> score
- **Dependencies**: C++ compiler, PyTorch, Boost, Zlib, (optional CUDA)
- **Runtime per eval**: ~1-60 minutes per benchmark
- **Pros**: Most freedom; can modify any algorithm part
- **Cons**: Impractical for iterative optimization (compilation time); fragile; large dependency surface

#### Alternative B: Parameter-only evolution
- **What agent does**: Outputs a JSON parameter file
- **Evaluation**: Pre-compiled baseline reads parameters -> runs placement -> score
- **Dependencies**: Same as A, but evaluator only needs compilation once
- **Runtime per eval**: ~1-60 minutes
- **Pros**: Lighter agent workspace; compile-once for evaluator
- **Cons**: Limits innovation to parameter space; cannot change algorithm structure

#### Alternative C (SELECTED): Output-based scoring
- **What agent does**: Produces a valid .pl placement file
- **Evaluation**: Pure-Python reader + HPWL calculator + legality checker
- **Dependencies**: NumPy, SciPy (for legality checks)
- **Runtime per eval**: ~seconds (just scoring)
- **Pros**: Minimal dependencies; fast iteration; clean separation of concerns
- **Cons**: Agent must run placer externally; evaluator cannot enforce HOW placement is done

#### Alternative D: Hybrid (recommended future path)
- **What agent does**: Runs provided Docker image with full placer; modifies placer code
- **Evaluation**: Agent-modified placer produces .pl file -> pure-Python scoring
- **Dependencies**: For evaluation: NumPy only. For agent: Docker/Python env with full compilation
- **Runtime per eval**: ~minutes for placer + ~seconds for scoring
- **Pros**: Best tradeoff; agent has full algorithmic freedom; evaluator is lightweight
- **Cons**: Two separate environments to maintain

**Final Decision**: **Alternative C initially** (pure output scoring), with migration path to Alternative D if maintainers require full reproducibility.

**Rationale**:
1. Evaluator must be fast, deterministic, and dependency-light for iterative optimization
2. HPWL computation needs only netlist topology + pin positions - no need to re-run placement
3. Legality checking (site capacity, carry chains) can be done from output .pl + static benchmark data
4. Agent is still free to use full aug-elfPlace baseline (or any other placer) to produce solution
5. Follows Frontier-Engineering principle of "frozen verifier scoring"

### 3.2 Selected Design: Agent Contract

```
Agent PROVIDES:
  - A valid .pl file (Bookshelf format placement solution)

Evaluator COMPUTES:
  - HPWL (via independent NumPy computation over netlist)
  - Legality gates (site-type, capacity, carry-chain, clock-region)
  - Overflow (density-based)
  - Combined score: -HPWL if legal, INVALID_COMBINED_SCORE otherwise

FIXED (read-only for agent):
  - All benchmark files (.nodes, .nets, .scl, .lib, .lc, .clk)
  - The evaluator code (verification/evaluator.py)
  - The evaluation framework (frontier_eval/)
  - Task documentation (README.md, Task.md)

Editable by agent:
  - scripts/init.py (the placer algorithm, with EVOLVE-BLOCK markers)
  - Any additional helper files the agent adds under scripts/
```

### 3.3 Final Directory Structure

```
benchmarks/FPGA/ClockAwarePlacement/
|-- README.md                           Navigation doc
|-- README_zh-CN.md                     (Optional) Chinese version
|-- Task.md                             Core task contract
|-- Task_zh-CN.md                       (Optional) Chinese version
|
|-- references/                         Benchmark datasets (read-only)
|   |-- fpga-example1/                  ISPD FPGA-example1 benchmark
|   |   |-- design.aux, .nodes, .nets, .pl, .scl, .lib, .wts, .lc
|   |-- ispd2016/                       Full ISPD 2016 suite (12 designs)
|   |   |-- FPGA01/ .. FPGA12/
|   |-- clock_constraints/              NEW: Clock region constraint files
|   |   |-- fpga-example1.clk
|   |   |-- FPGA01.clk .. FPGA12.clk
|   +-- problem_config.json             Unified problem configuration
|
|-- baseline/                           Reference solution (aug-elfPlace)
|   |-- dreamplacefpga/                 Core placer package
|   |-- CMakeLists.txt, requirements.txt, paramsFPGA.json
|   +-- README.md
|
|-- scripts/                            Agent-editable code
|   |-- init.py                         Initial baseline (with EVOLVE-BLOCK)
|   +-- requirements.txt                Agent dependencies
|
|-- verification/                       Frozen evaluator (NOT editable)
|   |-- evaluator.py                    Core scoring entry point
|   |-- canonical.py                    Ref: HPWL computation, parsers, legality checks
|   +-- requirements.txt                Evaluator dependencies (NumPy)
|
|-- frontier_eval/                      Unified-task metadata
|   |-- initial_program.txt, eval_command.txt, eval_cwd.txt
|   |-- agent_files.txt, readonly_files.txt, constraints.txt
|   |-- copy_files.txt, candidate_destination.txt, artifact_files.txt
|   |-- evaluator.py                    Thin wrapper -> verification/evaluator.py
|   +-- run_eval.py                     Boilerplate runner
|
|-- runtime/                            (Optional) Shared runtime modules
+-- tests/                              (Optional) Test harness
```

**Key additions to existing directory**:
- references/clock_constraints/ -- NEW: clock region constraint files
- references/problem_config.json -- NEW: unified configuration
- scripts/requirements.txt -- NEW: agent dependency file
- verification/canonical.py -- NEW: independent reference (parsers, HPWL, legality)
- runtime/ -- (Optional) shared modules

## 4. Evaluation Design

### 4.1 Architectural Decision: Pure-Python Output Evaluator

The evaluator reads the candidate output .pl file and computes scores independently.
It does NOT run the placer itself. Rationale:

1. **Speed**: Scoring takes seconds, not hours
2. **Determinism**: No compilation variance, no GPU nondeterminism
3. **Portability**: Pure Python + NumPy only
4. **Fairness**: All candidates judged by the same frozen code

### 4.2 Evaluator Interface (pseudocode)

```python
# verification/evaluator.py

INVALID_COMBINED_SCORE = -1e18

def evaluate(program_path: str, *, repo_root: Path | None = None) -> dict:
    \"\"\"
    Full evaluation pipeline.
    
    1. Run candidate program to produce .pl file
    2. Parse output .pl to extract node positions
    3. Load benchmark data
    4. Compute HPWL (independent NumPy computation)
    5. Check legality gates
    6. Compute combined score
    7. Return metrics dict
    \"\"\"
    start = time.time()
    metrics = {
        "combined_score": INVALID_COMBINED_SCORE,
        "valid": 0.0,
        "runtime_s": 0.0,
        "hpwl": float("inf"),
        "overflow": float("inf"),
        "legality_site_type": 0.0,
        "legality_capacity": 0.0,
        "legality_carry_chain": 0.0,
        "legality_clock_region": 0.0,
    }

    # Step 1: Run candidate
    result = subprocess.run([sys.executable, program_path], ...)

    # Step 2: Parse output .pl
    pl_path = find_output_pl(work_dir, program_path)
    node_positions = parse_pl(pl_path)

    # Step 3: Load benchmark
    benchmark = load_benchmark(repo_root)

    # Step 4: Compute HPWL (independent - in canonical.py)
    hpwl = compute_hpwl_canonical(
        node_positions, benchmark.pin_offsets,
        benchmark.flat_net2pin, benchmark.netpin_start,
        benchmark.net_weights, benchmark.wl_weight_x, benchmark.wl_weight_y,
    )
    metrics["hpwl"] = hpwl

    # Step 5: Legality gates
    metrics["legality_site_type"] = 1.0 if check_site_type_compatibility(...) else 0.0
    metrics["legality_capacity"] = 1.0 if check_site_capacity(...) else 0.0
    metrics["legality_carry_chain"] = 1.0 if check_carry_chain(...) else 0.0
    metrics["legality_clock_region"] = 1.0 if check_clock_region(...) else 0.0

    # Step 6: Overflow
    metrics["overflow"] = compute_density_overflow(...)

    # Step 7: Combined score
    all_legal = all([
        metrics["legality_site_type"],
        metrics["legality_capacity"],
        metrics["legality_carry_chain"],
        metrics["legality_clock_region"],
    ])
    if all_legal:
        metrics["valid"] = 1.0
        overflow_penalty = max(0.0, metrics["overflow"] - 0.10) * HPWL_SCALE
        metrics["combined_score"] = -(hpwl + overflow_penalty)
    else:
        metrics["valid"] = 0.0
        metrics["combined_score"] = INVALID_COMBINED_SCORE

    metrics["runtime_s"] = time.time() - start
    return _wrap(metrics, artifacts)
```

### 4.3 Score Formula

```
combined_score = -(HPWL + overflow_penalty)
               = -(HPWL + max(0, overflow - 0.10) * HPWL_SCALE)
```

### 4.4 JSON Output Schema

```json
{
    "combined_score": -12345.67,
    "valid": 1.0,
    "runtime_s": 42.5,
    "hpwl": 12345.67,
    "overflow": 0.05,
    "legality_site_type": 1.0,
    "legality_capacity": 1.0,
    "legality_carry_chain": 1.0,
    "legality_clock_region": 1.0,
    "timeout": 0.0
}
```

### 4.5 Independent Reference: canonical.py

```python
# verification/canonical.py (pseudocode)

def compute_hpwl_canonical(...) -> float:
    \"\"\"HPWL using pure NumPy. Matches hpwl.cpp algorithm exactly.\"\"\"
    # For each net, get pin positions, compute (max-min)*weight, sum

def parse_pl(filepath) -> dict: ...
def parse_nodes(filepath) -> dict: ...
def parse_nets(filepath) -> dict: ...
def parse_scl(filepath) -> dict: ...
def parse_lib(filepath) -> dict: ...
def parse_lc(filepath) -> dict: ...

def check_site_type_compatibility(...) -> bool: ...
def check_site_capacity(...) -> bool: ...
def check_carry_chain_integrity(...) -> bool: ...
def check_clock_region_constraints(...) -> bool: ...
def compute_density_overflow(...) -> float: ...
```

### 4.6 Evaluation Modes

| Mode | What happens | When used |
|------|-------------|-----------|
| Scoring | Full eval: run candidate -> score | During optimization |
| Validation | Score-only: read existing .pl -> score | Baseline verification |
| Debug | Score-only with verbose logging | Development |

## 5. Task.md Outline

### 5.1 Outline Structure

```markdown
# Clock-Aware FPGA Placement

## 1. Background
- FPGA placement problem overview
- Why clock distribution matters in FPGAs
- Clock region constraints in modern FPGA architectures
- The wirelength-vs-clock-quality tradeoff
- Relevance: ISPD 2016 contest benchmarks, aug-elfPlace baseline

## 2. Problem Formulation
- **Input**: ISPD bookshelf format (.nodes, .nets, .pl, .scl, .lib, .lc) + clock constraints (.clk)
- **Output**: Legal placement file (.pl) in Bookshelf format
- **Optimization objective**: Minimize half-perimeter wirelength (HPWL)
- **Subject to**: Site legality + clock region constraints

## 3. Input File Specification
- .nodes: Instance list with cell types
- .nets: Netlist connectivity
- .pl: Initial placement (reference positions)
- .scl: Site constraints (types, capacities, grid)
- .lib: Cell library (pin directions, clock/control signals)
- .lc: Legality constraints (site dimensions, LUT fracture, FF control signals)
- .clk: Clock region definitions (NEW: boundaries, domain assignments, constraints)

## 4. Design Variables
- For each movable instance: (x, y, z) site coordinates
- x, y are integer site grid coordinates
- z encodes intra-site position (for multi-element sites)

## 5. Scoring

### 5.1 Primary Metric
- **HPWL** (half-perimeter wirelength) — lower is better
- Computed by the frozen evaluator using an independent NumPy implementation
- Aggregated across multiple benchmark designs (12 ISPD designs)

### 5.2 Hard Validation Gates
- **G1 — Site-type compatibility**: Every instance on a site matching its resource type
- **G2 — Site capacity**: No site exceeds resource capacity (LUTs/slice, FFs/slice)
- **G3 — Carry-chain integrity**: Carry chains in adjacent sites, correct order
- **G4 — Clock region constraint**: Clock-domain-aware placement within legal regions

### 5.3 Combined Score
- Fully legal: combined_score = -HPWL (negated for maximization)
- Any gate fails: combined_score = INVALID_COMBINED_SCORE (-1e18)
- Soft overflow penalty: combined_score = -(HPWL + max(0, overflow-0.10) * scale)

## 6. Submission Format
- Output file: solution.pl (or equivalent .pl path)
- Format: name x y z per line, /FIXED suffix for fixed instances
- The evaluator reads this file to compute scores

## 7. Evaluation
- Frozen evaluator at verification/evaluator.py
- Independent reference at verification/canonical.py
- Pure Python + NumPy — no compilation needed
- Run: python verification/evaluator.py scripts/init.py

## 8. Baseline
- aug-elfPlace (DREAMPlaceFPGA) with default parameters
- Provides wirelength-optimized placement without clock awareness
- Available under baseline/

## 9. Verification
- python verification/evaluator.py scripts/init.py
- python -m frontier_eval task=unified task.benchmark=FPGA/ClockAwarePlacement algorithm.iterations=0
```

### 5.2 Key Design Decisions for Task.md

1. **Clock constraints are new input files** (.clk) defining clock domains and clock region boundaries
2. **The clock gate is a hard validation gate** — scattershot placement across clock regions is invalid
3. **HPWL remains the primary continuous metric** — clock adds a constraint, not a new objective term
4. **Multi-benchmark aggregation** — evaluation runs across multiple ISPD designs for robustness

## 6. Risk Review

### R1: Large benchmark dataset size
- **Risk**: ISPD suite ~166 MB, Titan23 ~500 MB
- **Solution**: Use FPGA-example1 for fast iteration, ISPD suite for final scoring
- **Mitigation**: Include all 12 ISPD designs but compress as tar.gz

### R2: Long evaluation runtime
- **Risk**: Full placement takes 1-60 minutes per design
- **Solution**: Evaluator does NOT run placement; only scores output (~seconds)
- **Mitigation**: Clear documentation that agent must produce .pl externally

### R3: Missing dependencies for agent
- **Risk**: Full baseline requires C++ compiler, CMake, Boost, Zlib, PyTorch, (CUDA)
- **Solution**: Provide pre-built Docker image with compiled baseline
- **Mitigation**: Document two paths: light (NumPy-only scoring) and full (with baseline Docker)

### R4: Non-determinism
- **Risk**: GPU placement can be non-deterministic; overflow depends on binning
- **Solution**: Use CPU-only evaluation; set seed=42; use fixed binning resolution
- **Mitigation**: Evaluator is deterministic by design (pure NumPy)

### R5: PyTorch dependency
- **Risk**: Full baseline requires PyTorch (~2GB)
- **Solution**: Evaluator is PyTorch-free; agent may need PyTorch
- **Mitigation**: Provide Docker for agent environment

### R6: C++ compilation
- **Risk**: All ops require compilation via CMake
- **Solution**: Provide pre-compiled wheels or Docker image
- **Mitigation**: Target Linux; document Windows as unsupported for baseline compilation

### R7: Clock constraint definition
- **Risk**: aug-elfPlace has zero clock awareness built in
- **Solution**: Clock constraints are NEW — not present in baseline
- **Mitigation**: Provide clock constraint parser; reference literature on clock-aware placement

### R8: Frontier unified-task compatibility
- **Risk**: Unified task requires specific metadata format
- **Solution**: Follow exact pattern from TopologyOptimization
- **Mitigation**: Verify against CONTRIBUTING.md and existing unified tasks

### R9: Agent workspace size
- **Risk**: Full baseline ~1.5 GB with third-party; copy_files=. would be too large
- **Solution**: Set copy_files.txt to minimal set (only scripts/init.py)
- **Mitigation**: Reference data stays readonly; agent only needs editable entry point

### R10: Scoring fairness across designs
- **Risk**: Larger designs have larger HPWL -> dominate aggregate score
- **Solution**: Normalize HPWL by baseline HPWL per design
- **Mitigation**: Aggregate as mean(HPWL_norm) = mean(HPWL_design / HPWL_baseline_design)

## 7. Implementation Roadmap

### Phase A: Foundation (Week 1)

**Step A1**: Update README.md and Task.md with proper descriptions (not placeholders)
- *Testable*: Render documents and review

**Step A2**: Create verification/canonical.py with pure-Python parsers
- Files: .nodes, .nets, .pl, .scl, .lib, .lc, .clk
- *Testable*: python -c "from canonical import parse_nodes; ..." on real benchmark files

**Step A3**: Implement HPWL computation in canonical.py
- Match hpwl.cpp algorithm exactly
- *Testable*: Compare HPWL against baseline computation on same solution

**Step A4**: Create verification/evaluator.py scaffold
- evaluate(program_path) -> metrics dict
- *Testable*: python evaluator.py scripts/init.py on known-good solution

### Phase B: Core Scoring (Week 2)

**Step B1**: Implement legality gates in canonical.py
- Site-type, capacity, carry-chain gates
- *Testable*: Each gate returns boolean on known-legal and known-illegal solutions

**Step B2**: Implement clock region gate in canonical.py
- Parse .clk files; check clock domain -> region mapping
- *Testable*: Gate on known clock-aware placement

**Step B3**: Implement overflow computation in canonical.py
- Density binning + overflow ratio
- *Testable*: Compare against baseline EvalMetricsFPGA

**Step B4**: Wire up verification/evaluator.py with scoring
- Combined score formula, metrics output
- *Testable*: python evaluator.py baseline/solution.pl -> metrics.json

### Phase C: Benchmark Data (Week 2-3)

**Step C1**: Create clock constraint files for each benchmark
- references/clock_constraints/FPGA01.clk etc.
- Extract clock domains from original design data
- Define clock region boundaries
- *Testable*: Parse each .clk file and validate

**Step C2**: Create references/problem_config.json
- Unified config for all benchmark designs
- *Testable*: All fields parse correctly

**Step C3**: Copy full ISPD 2016 suite into references/ispd2016/
- *Testable*: Each design passes I/O parsing

### Phase D: Scripts and Integration (Week 3)

**Step D1**: Create scripts/init.py with EVOLVE-BLOCK markers
- Baseline = run aug-elfPlace with default params
- Clear ALLOWED/NOT ALLOWED documentation
- *Testable*: python scripts/init.py produces a .pl file

**Step D2**: Create scripts/requirements.txt
- Dependencies for running the placer
- *Testable*: pip install -r scripts/requirements.txt

**Step D3**: Create verification/requirements.txt
- NumPy only
- *Testable*: pip install succeeds in clean environment

**Step D4**: Create frontier_eval/ metadata files
- All 11 metadata files following unified pattern
- *Testable*: python -m frontier_eval task=unified task.benchmark=FPGA/ClockAwarePlacement algorithm.iterations=0

### Phase E: Validation (Week 3-4)

**Step E1**: Validate scoring on baseline solution
- Run baseline -> .pl -> score -> verify HPWL matches
- *Testable*: python verification/evaluator.py scripts/init.py produces expected metrics

**Step E2**: Validate on known-illegal solutions
- Artificially corrupt solution -> confirm gates catch it
- *Testable*: Each gate independently triggers failure

**Step E3**: Validate unified framework integration
- Full task=unified smoke test
- *Testable*: algorithm.iterations=0 passes

**Step E4**: Performance benchmark
- Measure scoring time across all 12 ISPD designs
- Target: < 5 seconds per design for scoring
- *Testable*: Timing report produced

### Phase F: Polish (Week 4)

**Step F1**: Write README.md (full version)
**Step F2**: Write Task.md (full version)
**Step F3**: Add Chinese translations (zh-CN variants)
**Step F4**: Final review against CONTRIBUTING.md checklist
**Step F5**: Create Docker image for reproducible agent environment (if needed)

---

## Appendix: EVOLVE-BLOCK Design for scripts/init.py

```python
# EVOLVE-BLOCK-START
\"\"\"
Clock-Aware FPGA Placement

- ALLOWED TO MODIFY: optimize_placement() - the core optimization algorithm
- ALLOWED TO MODIFY: run_placement() - the main entry point for the placer
- NOT ALLOWED TO MODIFY: load_benchmark() - interface must match evaluator
- NOT ALLOWED TO MODIFY: The output .pl file format
- NOT ALLOWED TO MODIFY: The function signature of run_placement()
\"\"\"

import ... (standard library imports)

# ============================================================
# DATA LOADING (NOT ALLOWED TO MODIFY)
# ============================================================
def load_benchmark(benchmark_path: str) -> dict:
    \"\"\"Load benchmark data. Must match evaluator input contract.\"\"\"
    ...

def load_clock_constraints(clk_path: str) -> list:
    \"\"\"Load clock region constraints. Must match evaluator format.\"\"\"
    ...

# ============================================================
# PLACEMENT OPTIMIZATION (ALLOWED TO MODIFY)
# ============================================================
def optimize_placement(benchmark: dict, clock_constraints: list) -> dict:
    \"\"\"
    Run placement optimization. This is the main evolvable function.
    
    Default: Uses aug-elfPlace with default parameters.
    Agent should improve by:
    1. Adding clock-aware density terms to objective
    2. Modifying optimization stages and hyperparameters
    3. Adding clock-region constraint handling
    4. Improving legalization for clock regions
    \"\"\"
    placement = run_aug_elfplace(benchmark)
    return placement

# ============================================================
# OUTPUT (NOT ALLOWED TO MODIFY - format must match evaluator)
# ============================================================
def write_placement(placement: dict, output_path: str):
    \"\"\"Write .pl file in Bookshelf format.\"\"\"
    ...

def main():
    benchmark = load_benchmark(...)
    clock_constraints = load_clock_constraints(...)
    placement = optimize_placement(benchmark, clock_constraints)
    write_placement(placement, "solution.pl")

if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
```

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2026-07-09 | Initial design report |
