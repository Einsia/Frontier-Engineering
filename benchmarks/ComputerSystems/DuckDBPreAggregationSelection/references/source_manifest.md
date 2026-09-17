# Source Manifest

- Upstream engine: `DuckDB`
- Upstream lineage:
  - DuckDB benchmark and TPC-H documentation
  - DuckDB SQL execution on analytical reporting queries
- Schema lineage: this benchmark uses a local frozen relational workload with `customer`, `orders`, and `lineitem` tables modeled after the TPC-H schema family.
- Data provenance: rows are generated deterministically inside DuckDB from fixed SQL formulas and a fixed schema; this is a benchmark-local synthetic dataset, not official TPC-H `dbgen` output.
- Authenticity note: the reporting queries and schema family are traceable to official analytical benchmark patterns, while the candidate pre-aggregations are benchmark-local frozen physical-design options.
- License lineage: DuckDB is released under the MIT License.
