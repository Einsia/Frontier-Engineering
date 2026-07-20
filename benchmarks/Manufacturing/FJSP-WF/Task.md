# Task: FJSP-WF (Flexible Job Shop Scheduling with Worker Flexibility)

## Audience and Assumptions

This task assumes you have general CS/programming background but little or no prior scheduling knowledge.

## Engineering Background

### This Is a Real Manufacturing Problem

FJSP-WF models a decision that production engineers face every day in factories worldwide: given a set of customer orders (jobs), each requiring a sequence of production steps (operations), available machines, and a team of workers with different skill levels, how should the work be scheduled to finish as early as possible?

This is not a toy problem or a purely mathematical puzzle. It is a core operations challenge that manufacturing companies invest significant resources to solve. Before the rise of AI coding agents, this class of problems was addressed by:

- **Human scheduling experts** using heuristic rules and experience
- **Operations research engineers** building mathematical optimization models (MILP, constraint programming)
- **Production planning systems** implementing dispatching rules and local search heuristics
- **Industrial engineers** performing time studies and bottleneck analysis

The economic stakes are high: a 1% improvement in production makespan translates directly into increased throughput, lower energy costs per unit, and better on-time delivery performance.

### What This Benchmark Evaluates

This benchmark evaluates whether an AI agent can improve an **existing engineering scheduling artifact** 鈥?not whether it can generate a schedule from scratch, and not whether it can solve a math problem.

The agent receives:

1. A **working but suboptimal** scheduling program (`scripts/init.py`) with a simple greedy algorithm
2. A **task description** explaining the manufacturing problem, the input data format, and the objective
3. A **scoring evaluator** that objectively measures schedule quality

The agent must:

1. **Read and understand** the existing scheduling code
2. **Identify improvement opportunities** (better operation sequencing, smarter machine assignment, more efficient worker allocation)
3. **Modify the code** to produce better schedules
4. **Iterate** based on quantitative feedback from the evaluator

This mirrors how a human engineer would improve a production planning system: understand the current logic, propose enhancements, test them against real data, and refine.

### Why Worker Flexibility Matters

Classical FJSP research assumes that any worker assigned to a machine can perform at the same speed. In reality, worker skill differences are significant:

- An experienced machinist may complete a setup in half the time of a trainee
- Some workers specialize in certain machines and are faster on them
- Cross-training levels vary across the workforce

FJSP-WF captures this reality. The scheduling algorithm must decide not only **which machine** to use but also **which worker** to assign, balancing workload across both dimensions.

## Problem Background

**Flexible Job Shop Scheduling (FJSP)** is a fundamental optimization problem in manufacturing systems. It extends the classical Job Shop Scheduling Problem (JSSP) by allowing each operation to be processed on **multiple eligible machines**, rather than a single fixed machine.

**FJSP-WF** (Worker Flexibility) further extends FJSP by introducing a **worker dimension**:
- Each machine can be operated by multiple workers
- Different workers may have different processing speeds on the same machine
- Each worker can operate only one machine at a time

The result is a three-dimensional assignment problem: for each operation, the scheduler must decide:
1. **Which machine** should process it
2. **Which worker** should operate that machine
3. **When** it should start

### Problem Formulation

An FJSP-WF instance consists of:

- A set of **Jobs** `J = {J_1, ..., J_n}`, each job is a sequence of **Operations**
- A set of **Machines** `M = {M_1, ..., M_m}`
- A set of **Workers** `W = {W_1, ..., W_w}`
- Each operation `O_{j,k}` (k-th operation of job j) has:
  - A set of eligible machines `M_{j,k} 鈯?M`
  - For each eligible machine `m 鈭?M_{j,k}` and each worker `w 鈭?W`, a processing time `p_{j,k,m,w}`

### Constraints

1. **Precedence constraint**: For each job, operation `k+1` cannot start before operation `k` finishes.
2. **Machine constraint**: A machine can process at most one operation at a time.
3. **Worker constraint**: A worker can operate at most one machine at a time.
4. **Eligibility constraint**: An operation can only be assigned to an eligible machine.
5. **Worker-skill constraint**: A worker can only operate machines they are qualified for.
6. **Non-preemption**: Once started, an operation runs to completion without interruption.

### Objective

Minimize the **makespan** (total completion time): `C_max = max(C_j)` where `C_j` is the completion time of job `j`.

## Instance Format (.fjswf)

FJSP-WF instances use the `.fjswf` (Flexible Job Shop with Worker Flexibility) extension.

Each `.fjswf` file is a JSON document with the following structure:

```json
{
    "name": "synthetic_01",
    "description": "Human-readable description",
    "num_jobs": 2,
    "num_machines": 2,
    "num_workers": 2,
    "operations": [
        {
            "job_id": 0,
            "op_idx": 0,
            "eligible_machines": [0, 1],
            "processing_times": [
                [3, 2],
                [4, 3]
            ]
        }
    ],
    "worker_eligibility": [
        [0, 1],
        [0, 1]
    ],
    "metadata": {
        "best_known_makespan": null,
        "lower_bound": null,
        "source": "synthetic example for smoke testing"
    }
}
```

Fields:

- `name`: Instance identifier
- `num_jobs` / `num_machines` / `num_workers`: Problem dimensions
- `operations`: List of all operations across all jobs
  - `job_id`: Job index (0-based)
  - `op_idx`: Operation index within the job (0-based)
  - `eligible_machines`: List of machine IDs that can process this operation
  - `processing_times`: 2D array where `processing_times[i][j]` is the processing time when using machine `eligible_machines[i]` and worker `j`.
- `worker_eligibility`: 2D array where `worker_eligibility[w]` lists machine IDs that worker `w` can operate.
- `metadata`: Optional metadata about the instance.

## Instance Data

## Instance Data

This benchmark uses two categories of instances:

### Official Benchmark Instances (30 files)

The primary benchmark data consists of 30 official FJSSP-W instances from the **GECCO FJSSP-WU Competition** (Apache-2.0 license). These are located in `data/instances/official/` as `.fjs` files and include native worker flexibility data.

| Family | Instances | Jobs × Machines | Workers |
|--------|-----------|-----------------|---------|
| BehnkeGeiger | 3 | 10×15 to 20×20 | 42-60 |
| Brandimarte | 3 | 20×5 to 20×15 | 7-14 |
| Hurink sdata | 8 | 6×6 to 30×10 | 1-63 |
| Hurink edata | 2 | 6×6 to 10×6 | 1-6 |
| Hurink rdata | 3 | 15×10 to 30×10 | 28-50 |
| Hurink vdata | 3 | 10×6 to 15×15 | 5-30 |
| DPpaulli | 4 | 5×5 to 20×15 | 1-18 |
| ChambersBarnes | 1 | 15×11 | 10 |
| Kacem | 2 | 10×7 to 15×10 | 3-4 |
| Fattahi | 2 | 5×3 to 8×5 | 14-20 |

Each instance can be referenced by its competition filename, a short alias, or directly by filename stem. See `data/benchmark_instances.json` for the full registry.

### Synthetic Instances (3 files, CI only)

Located in `data/instances/synthetic/`, these are small `.fjswf` JSON instances for CI smoke testing only:

| Instance | Jobs | Machines | Workers | Operations |
|----------|------|----------|---------|------------|
| synthetic_01 | 2 | 2 | 2 | 4 |
| synthetic_02 | 3 | 3 | 2 | 7 |
| synthetic_03 | 4 | 3 | 3 | 9 |

**These synthetic instances are not benchmark data.** They exist only to verify evaluator correctness and framework integration.

See `data/sources.md` for complete data provenance and attribution.

## Input / Output## Input / Output Specification

### Solver Interface

The file `scripts/init.py` must export the following function:

```python
def solve_instance(instance: dict) -> dict:
    """
    Args:
        instance: dict with keys as described in the .fjswf format above.

    Returns:
        dict with:
            - name: str, instance name
            - makespan: int, computed makespan
            - machine_schedules: list[list[dict]], one list per machine
    """
```

### Output Format

The `machine_schedules` field is a list indexed by machine ID. Each element is a list of operation dicts:

```
machine_schedules[machine_id] = [
    {
        "job_id": 0,
        "operation_index": 0,
        "machine_id": 0,
        "worker_id": 1,
        "start_time": 0,
        "end_time": 3,
        "duration": 3
    },
    ...
]
```

### Validation Rules

The evaluator (`verification/evaluator.py`) validates every schedule against the following checks. Each high-level rule may include multiple sub-checks for data integrity. Any single violation results in `score = 0.0` for that instance.

**1. All operations are scheduled exactly once**
   - Each operation appears at most once across all machine schedules (no duplicates)
   - Every operation from the instance appears in the schedule (no missing operations)

**2. Job precedence constraint**
   - For each job, operation `k+1` starts after operation `k` ends

**3. Machine non-overlap**
   - No two operations overlap in time on the same machine

**4. Worker non-overlap**
   - No worker is assigned to overlapping operations on different machines

**5. Machine eligibility**
   - Each operation is assigned to a machine listed in its `eligible_machines`

**6. Worker eligibility**
   - Each worker is qualified to operate the assigned machine, as defined by `worker_eligibility`

**7. Processing time integrity**
   - The scheduled duration matches the `processing_times[machine][worker]` lookup value from the instance data

**8. Output structure integrity**
   - `machine_schedules` length matches `num_machines`
   - Each machine schedule is a list of dicts containing all required fields:
     `job_id`, `operation_index`, `machine_id`, `worker_id`, `start_time`, `end_time`, `duration`
   - All field values have correct types and refer to valid jobs, operations, machines, and workers
   - The `machine_id` field in each schedule entry matches its parent schedule index

**9. Temporal consistency**
   - All start times are non-negative
   - `end_time >= start_time` for every operation
   - `duration == end_time - start_time` (internal consistency)

## Scoring

### Score Formula

For each instance:

```
score_i = baseline_makespan_i / agent_makespan_i
```

- If the agent schedule is invalid (any validation check fails): `score_i = 0.0`
- If `agent_makespan < baseline_makespan`: `score_i > 1.0` (improvement)
- If `agent_makespan == baseline_makespan`: `score_i = 1.0` (equal)
- If `agent_makespan > baseline_makespan`: `0.0 < score_i < 1.0` (worse)

### Aggregate Score

```
combined_score = mean(score_i for all instances)
```

The score is continuous, allowing partial credit and iterative improvement tracking across multiple evaluation rounds.

## Implementations in This Folder

- `baseline/solution.py`: Greedy EST+SPT (Earliest Start Time + Shortest Processing Time) list scheduling. Pure Python, standard library only. **Read-only** 鈥?serves as the fixed baseline for relative scoring.
- `scripts/init.py`: **Agent-editable artifact**. Starts with the same EST+SPT baseline algorithm. The agent must modify the code inside the EVOLVE-BLOCK markers to improve scheduling performance.
- `verification/evaluator.py`: **Read-only** scoring and validation script. Dynamically loads both baseline and candidate solver, executes them on all instances, validates output, and computes scores.

## How to Run

### Run Baseline Only

```bash
python scripts/init.py --max-instances 3
```

### Run Evaluator

```bash
python verification/evaluator.py scripts/init.py
```

### Run Evaluator on Specific Instances

```bash
python verification/evaluator.py scripts/init.py --instances synthetic_01 synthetic_02
```

### Run Unified Framework (from repo root)

```bash
python -m frontier_eval task=unified task.benchmark=Manufacturing/FJSP-WF algorithm=openevolve algorithm.iterations=0
```

## Agent Constraints

1. Only modify code between `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` markers in `scripts/init.py`.
2. Keep the marker lines `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` intact 鈥?they define the only editable region.
3. Do not modify `verification/evaluator.py`, `baseline/solution.py`, or any file outside `scripts/init.py`.
4. Pure Python implementation only (standard library allowed).
5. No external solvers (OR-Tools, CPLEX, Gurobi, PuLP, etc.).
6. No external libraries (numpy, pandas, scipy, etc.).
7. No API calls or network access.
8. Keep the `solve_instance` function signature and output format unchanged.
