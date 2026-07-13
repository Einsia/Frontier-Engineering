# Problem Formulation: FJSP-WF

## Formal Definition

### Sets and Indices

- `J = {1, ..., n}` — set of jobs
- `M = {1, ..., m}` — set of machines
- `W = {1, ..., w}` — set of workers
- `O_j` — set of operations for job `j`, where `O_j = {O_{j,1}, ..., O_{j,n_j}}`
- `M_{j,k} ⊆ M` — set of eligible machines for operation `O_{j,k}`

### Parameters

- `p_{j,k,m,w}` — processing time of operation `O_{j,k}` on machine `m` with worker `w`
- `elig_{w,m} ∈ {0, 1}` — 1 if worker `w` is qualified to operate machine `m`

### Decision Variables

- `x_{j,k,m,w} ∈ {0, 1}` — 1 if operation `O_{j,k}` is assigned to machine `m` with worker `w`
- `s_{j,k} ≥ 0` — start time of operation `O_{j,k}` (integer)
- `c_{j,k} ≥ 0` — completion time of operation `O_{j,k}` (integer)

### Objective

Minimize makespan:
```
min C_max
```

### Constraints

**1. Machine and Worker Assignment:**
Each operation must be assigned to exactly one machine-worker pair:

```
∑_{m ∈ M_{j,k}} ∑_{w ∈ W: elig_{w,m}=1} x_{j,k,m,w} = 1,  ∀j, k
```

**2. Processing Time:**
```
c_{j,k} = s_{j,k} + ∑_{m ∈ M_{j,k}} ∑_{w ∈ W: elig_{w,m}=1} p_{j,k,m,w} · x_{j,k,m,w},  ∀j, k
```

**3. Job Precedence:**
Operation k+1 cannot start before operation k finishes:
```
s_{j,k+1} ≥ c_{j,k},  ∀j, k = 1, ..., n_j - 1
```

**4. Machine Capacity:**
A machine can process at most one operation at a time:
```
s_{j,k} ≥ c_{j',k'}  OR  s_{j',k'} ≥ c_{j,k}
∀(j,k) ≠ (j',k') where both use the same machine
```

**5. Worker Capacity:**
A worker can operate at most one machine at a time:
```
s_{j,k} ≥ c_{j',k'}  OR  s_{j',k'} ≥ c_{j,k}
∀(j,k) ≠ (j',k') where both use the same worker
```

**6. Makespan Definition:**
```
C_max ≥ c_{j, n_j},  ∀j
```

**7. Non-preemption:**
Once started, an operation runs without interruption.

**8. Eligibility:**
```
x_{j,k,m,w} = 0 if m ∉ M_{j,k} or elig_{w,m} = 0
```

## Complexity

FJSP-WF is NP-hard. It generalizes:
- **Job Shop Scheduling (JSP)**: NP-hard in the strong sense
- **Flexible Job Shop Scheduling (FJSP)**: NP-hard
- **FJSP-WF**: Adds the worker dimension, increasing the solution space combinatorially

## Solution Approaches

### Exact Methods
- Mixed-Integer Linear Programming (MILP)
- Constraint Programming (CP)
- Branch and Bound

### Heuristic Methods
- Priority Dispatch Rules (e.g., EST+SPT, MWKR, MOD)
- Greedy Randomized Adaptive Search Procedure (GRASP)
- Tabu Search
- Simulated Annealing

### Metaheuristic Methods
- Genetic Algorithm (GA)
- Particle Swarm Optimization (PSO)
- Artificial Bee Colony (ABC)
- Shuffled Frog Leaping Algorithm (SFLA)

The current baseline implements a simple EST+SPT greedy dispatch rule.