# Source Manifest

- Upstream engine: `DuckDB`
- Upstream lineage:
  - DuckDB benchmark and TPC-H documentation
  - DuckDB SQL optimizer and query execution model
- Schema lineage: this benchmark uses a local frozen relational workload with `customer`, `orders`, and `lineitem` tables modeled after the TPC-H schema family.
- Data provenance: rows are generated deterministically inside DuckDB from fixed SQL formulas and a fixed schema; this is a benchmark-local synthetic dataset, not official TPC-H `dbgen` output.
- Authenticity note: the workload shape is traceable to official DuckDB/TPC-H analytical reporting patterns, while the exact query instance is a benchmark-local frozen SQL task chosen to expose meaningful rewrite opportunities.
- License lineage: DuckDB is released under the MIT License.
