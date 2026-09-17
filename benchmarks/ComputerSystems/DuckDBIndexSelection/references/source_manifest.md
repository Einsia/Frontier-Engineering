# Source Manifest

- Upstream engine: `DuckDB`
- Upstream lineage:
  - DuckDB benchmark and TPC-H documentation
  - DuckDB SQL and index support
- Schema lineage: this benchmark uses a local frozen relational workload with `customer`, `orders`, and `lineitem` tables modeled after the TPC-H schema family.
- Data provenance: rows are generated deterministically inside DuckDB from fixed SQL formulas and a fixed schema; this is a benchmark-local synthetic dataset, not official TPC-H `dbgen` output.
- Authenticity note: the schema and workload lineage are traceable to official DuckDB/TPC-H benchmarking materials, but the data itself is a local frozen synthetic asset used because online extension-based generation was not reliable in this environment.
- License lineage: DuckDB is released under the MIT License.
