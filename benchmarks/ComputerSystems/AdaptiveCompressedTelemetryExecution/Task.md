# Task: Adaptive Compressed Telemetry Execution

## 1. Engineering problem

Telemetry backends continuously ingest timestamped events and later scan them for
incident response, dashboards, retention, and audit queries. Storing every field as
an uncompressed 64-bit value is fast but expensive. Aggressive compression can
reduce storage traffic while making ingestion, full decoding, or selective queries
more CPU-intensive. The useful engineering problem is therefore not compression in
isolation: it is joint design of a block representation and the operators that use
that representation.

The [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
defines common timestamp, severity, resource, and attribute concepts and explicitly
calls out efficient serialization and space use. Modern systems research similarly
co-designs compression and execution: the
[FastLanes file format](https://vldb.org/pvldb/vol18/p4629-afroozeh.pdf) uses
composable data-parallel encodings, multi-column relationships, partial decoding,
and compressed-vector access, while
[MorphStore](https://arxiv.org/abs/2004.09350) studies complete analytical pipelines
over compressed representations.

This benchmark presents the same open design space in a self-contained CPU task.
Candidate code is actually compiled and timed; there is no analytical prediction of
codec or query performance.

## 2. Logical schema

Every row contains five unsigned 64-bit columns:

| Index | Column | Meaning |
|---:|---|---|
| 0 | `timestamp_ns` | Event time in Unix nanoseconds; nondecreasing within a scenario |
| 1 | `service_id` | Service or tenant identifier |
| 2 | `severity` | OpenTelemetry-style numeric severity |
| 3 | `duration_us` | Request or operation duration in microseconds |
| 4 | `payload_bytes` | Event payload size in bytes |

Rows are divided into public `block_rows`-sized blocks. The candidate owns the
entire byte representation inside each block and may encode columns independently,
jointly, or adaptively.

## 3. Candidate API

The immutable declarations are in `verification/codec_api.h`:

```cpp
bool encode_block(const BlockView& input,
                  std::vector<std::uint8_t>& encoded);

bool decode_block(const EncodedView& encoded,
                  const MutableBlock& output);

std::uint64_t query_block(const EncodedView& encoded,
                          const QuerySpec& query);
```

`EncodedView` supplies the opaque bytes and row count to a fresh process. An encoded
block must therefore be self-contained; pointers, process-global state, source-file
references, and external side files are invalid representations.

`decode_block` must reproduce every original value exactly. The evaluator allocates
the output columns.

## 4. Exact query semantics

All ranges are inclusive and arithmetic uses unsigned 64-bit values. Inputs are
chosen so correct aggregates do not overflow.

- `CountEqual`: count rows where `filter_column == low`.
- `CountRange`: count rows where `low <= filter_column <= high`.
- `SumWhereEqual`: sum `value_column` where `filter_column == low`.
- `SumWhereRange`: sum `value_column` where
  `low <= filter_column <= high`.

A correct baseline may decode inside `query_block`. More advanced solutions can
answer from metadata, dictionaries, bit-packed vectors, learned residuals, or other
compressed representations.

## 5. Workloads

The evaluator generates three deterministic, multi-column datasets:

1. `steady_api_traffic`: regular timestamps, low service cardinality, and mostly
   informational events.
2. `bursty_multitenant_observability`: rotating hot tenants, burst boundaries,
   higher cardinality, and localized error periods.
3. `incident_distribution_shift`: correlated changes in service popularity,
   severity, duration, and payload during an incident.

Each scenario uses a separate seed and contains eight exact query templates covering
equality, ranges, conditional sums, time windows, hot values, and low-selectivity
conditions. The generator seed can be overridden by the evaluator CLI for robustness
testing.

## 6. Verification and measurement

The evaluator performs the following steps:

1. Enforce the source-size limit and compile the candidate with
   `g++ -std=c++20 -O3 -march=native`.
2. Generate each raw dataset outside the timed region.
3. Run encoding in a CPU-pinned child process after warm-up.
4. Delete the raw input, then start a fresh process to decode the encoded file.
5. Compare the complete decoded binary output byte-for-byte with the original.
6. Start another fresh process, execute every query over every block, and compare
   all integer results with an independent Python oracle.
7. Report median, minimum, and maximum wall time over the configured measured rounds.

File loading, compilation, encoded-file writing, decoded-file writing, and result
serialization are excluded from the timed regions. Candidate allocation and the
actual encode/decode/query functions are included. Each child is pinned to one CPU,
so the elapsed time is a practical single-core performance measurement. A memory
limit, process CPU limit, wall timeout, encoded-size limit, and output-file limit are
enforced.

The evaluator reports:

- encode and decode GiB/s;
- compressed-query batch GiB/s;
- encoded bytes and compression ratio;
- per-phase timing samples and peak resident memory; and
- cost components and score for every scenario.

## 7. Economic objective

Let:

- `r = encoded_bytes / logical_bytes`;
- `H_e`, `H_d`, and `H_q` be measured encode, full-decode, and fixed-query-batch
  core-hours extrapolated to one logical TiB;
- `P_s` be the public storage price coefficient in dollars per GiB-month;
- `P_c` be the public CPU price coefficient in dollars per core-hour; and
- `D` and `Q` be scenario-specific monthly full-decode and query-batch counts.

The scenario cost is:

```text
storage_cost = 1024 * r * P_s
cpu_cost     = P_c * (H_e + D * H_d + Q * H_q)
monthly_cost_per_logical_TiB = storage_cost + cpu_cost
```

The coefficients are versioned workload parameters, not claims about a particular
cloud vendor. They make the storage/CPU trade-off explicit while every performance
input to the formula comes from executed candidate code.

For scenario `i`:

```text
ratio_i = baseline_monthly_cost_i / candidate_monthly_cost_i
```

`combined_score` is the geometric mean of the three ratios. The raw starter is the
immutable baseline and scores exactly `1.0`; larger is better.

## 8. Correctness and resource gates

Any compilation error, timeout, crash, false return, oversized block, incomplete
decode, byte mismatch, query mismatch, or non-finite metric yields
`valid=0.0` and `combined_score=0.0`.

The public limits are in `references/problem_config.json`:

- candidate source: at most 1,000,000 bytes;
- encoded block: at most twice its raw bytes plus a small fixed allowance;
- process address space: 1 GiB;
- one pinned CPU per timed process; and
- no external libraries, assets, services, or network access.

The task permits portable C++, compiler intrinsics, adaptive block selection, and
self-contained metadata. Only the code inside the EVOLVE markers may change.
