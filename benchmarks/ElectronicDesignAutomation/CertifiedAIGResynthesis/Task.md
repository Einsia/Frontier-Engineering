# Certified, Budgeted AIG Resynthesis

## Engineering problem

Logic synthesis repeatedly replaces a subgraph with a cheaper equivalent one.
The hard part is not merely discovering Boolean identities: useful flows must
coordinate local choices on a shared DAG, reuse existing divisors, trade area
against depth, and never change any output function. A rewrite that looks good as
a tree can lose once fanout and reconvergence are considered.

This task exposes that problem directly. A C++ policy receives a mutable
and-inverter graph (AIG), proposes arbitrary local replacement AIGs, and obtains a
Boolean proof obligation for each proposal. The immutable runtime emits only
accepted transformations. A separate Python implementation then replays the
certificate and exhaustively checks each obligation before measuring the final
DAG. No probabilistic simulation is used for correctness.

The central open engineering question is how to search a large space of locally
equivalent expressions while making globally beneficial, DAG-aware decisions
under a strict rewrite budget. Equality-saturation scheduling, cut enumeration,
NPN-aware libraries, exact small-function synthesis, divisor selection, and
learned rewrite orchestration can all be explored inside the same interface.

## Boolean representation

Inputs are dense, combinational ASCII AIGER (`aag`) networks:

- node 0 is constant false and literal 1 is constant true;
- positive literal `2 * id` denotes a node;
- xor with 1 denotes complemented polarity; and
- every non-input node is a two-input AND.

The frozen evaluator deterministically constructs five engineering circuit
families from `references/problem_config.json`:

1. a 96-bit ripple-carry adder;
2. a 64-bit logical barrel shifter;
3. a 128-request fixed-priority arbiter;
4. a 48-rule, 12-bit-per-rule packet classifier; and
5. a 64-bit update of a 32-bit CRC state.

The front ends deliberately retain several semantically redundant lowering forms
that arise from mux expansion, guarding, repeated expressions, and generic
Boolean lowering. Workload bytes and SHA-256 digests are deterministic and are
reported in `artifacts.json`.

## Candidate interface

Only this function is editable:

```cpp
void optimize(certified_aig::Optimizer& optimizer);
```

The immutable class provides graph inspection plus two mutation calls:

```cpp
bool try_rewrite(
    uint32_t root,
    const std::vector<uint32_t>& leaves,
    const std::vector<uint32_t>& divisors,
    const std::vector<LocalAnd>& local_ands,
    uint32_t local_output);

bool replace(
    uint32_t root,
    uint32_t replacement_global_literal,
    const std::vector<uint32_t>& leaves);
```

Useful read methods include `first_and_id()`, `node_count()`, `is_and(id)`,
`is_active(id)`, `resolve(literal)`, `fanins(id)`, `output_literal(index)`,
`primary_support(root)`, and `truth_table(root, leaves, &table)`. Their
implementations and precise failure conditions are visible in
`verification/rewrite_runtime.hpp`.

`try_rewrite` may synthesize any acyclic local AIG. With `k` cut leaves and `d`
divisors, local literal references are:

- reference 0: false;
- references `1..k`: the positive boundary leaves;
- references `k+1..k+d`: supplied global divisor literals; and
- subsequent references: local AND results in order.

Each literal is encoded as `2 * reference + polarity`. A local AND may reference
only an earlier value. Divisors can lie outside the root cone, enabling real
DAG-aware reuse, but each divisor must be a function of the same cut leaves and
must not depend on the rewritten root.

## Certificate and formal validity

The candidate executable writes a line-oriented certificate. The immutable C++
runtime checks proposals before recording them, but that check is not trusted for
the score. `verification/evaluator.py` independently parses the original AAG and
replays every certificate line.

For a cut of `k <= 8` leaves, the checker:

1. confirms that every path through the current root cone terminates at a listed
   leaf or constant;
2. evaluates the old root on all `2^k` assignments;
3. independently evaluates every external divisor over the same assignments and
   rejects root-dependent divisors;
4. evaluates the proposed local AIG on all assignments;
5. requires bit-for-bit equality; and
6. only then redirects the root and appends replacement nodes.

Because every step is an exact equivalence and later steps operate on the graph
produced by earlier ones, the sequence is a compositional proof that all primary
outputs retain their original Boolean functions. The checker also detects cycles,
forward references, stale nodes, uncovered input paths, malformed certificates,
and resource-limit violations.

## Resource limits

The public limits are:

- at most 8 cut leaves;
- at most 16 external divisors per rewrite;
- at most 64 new ANDs per rewrite;
- at most 20,000 accepted rewrites per workload;
- at most 300,000 total nodes;
- a 16 MB certificate; and
- 4 seconds of candidate execution per workload by default.

The evaluator additionally limits process address space to 2 GiB and compiles
with `g++ -std=c++17 -O2`. Compilation time is not part of the candidate execution
budget, but it is included in reported evaluator wall time.

## Objective

After replay, the checker traverses only nodes reachable from primary outputs:

- `A`: number of reachable AND nodes; and
- `D`: maximum AND level from any primary input or constant to an output.

Let `A_b, D_b` be the frozen starter result and `A_c, D_c` the candidate result
for one workload. Its score is

```text
(A_b / A_c)^0.75 * (D_b / D_c)^0.25
```

`combined_score` is the geometric mean across all five workloads. The starter is
exactly 1.0. Invalid source edits, compilation failures, timeouts, altered inputs,
invalid certificates, or degenerate final graphs produce `valid=0.0` and score
0.0.

The initial policy performs constant propagation, idempotence/complement
simplification, and exact structural hashing. It intentionally leaves substantial
headroom for cut resynthesis, absorption, mux reasoning, balancing, and divisor
reuse.

## Reproducibility and direct evaluation

No network access or nondeterministic input is used. The workload builder, config,
baseline, C++ runtime, and Python proof checker are all included and marked
read-only by the unified evaluator.

```bash
python verification/evaluator.py scripts/init.cpp \
  --metrics-out metrics.json \
  --artifacts-out artifacts.json
```

`metrics.json` contains numeric leaderboard fields. `artifacts.json` contains the
per-workload input digests, baseline and candidate area/depth, rewrite counts,
truth-table rows checked, certificate digests, and process runtimes.
