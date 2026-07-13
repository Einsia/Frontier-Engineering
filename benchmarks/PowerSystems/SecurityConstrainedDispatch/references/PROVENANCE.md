# Data provenance

The MATPOWER case files in `references/pglib/` are copied without modification
from:

```text
repository: https://github.com/power-grid-lib/pglib-opf
release:    v23.07
commit:     dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3
```

PGLib-OPF is curated by the IEEE PES Task Force on Benchmarks for Validation of
Emerging Power System Algorithms. The upstream license is included as
`references/pglib/LICENSE`.

`references/scenarios.json` is generated deterministically by:

```bash
python references/build_scenarios.py
```

The manifest records SHA-256 hashes for every copied case. It contains selected
line contingencies, reference AC-OPF costs, and feasible non-optimal baseline
setpoints. Regenerate it only when deliberately updating the pinned cases or
solver versions.
