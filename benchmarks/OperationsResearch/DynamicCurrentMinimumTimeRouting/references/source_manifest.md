# Source Manifest

- Upstream lineage:
  - TU Delft CITG `HALEM` repository and README
  - Time-optimal ship routing with dynamic currents, variable velocity, and minimum-water-depth constraints
- License lineage: upstream code lineage is MIT.
- Data provenance: this benchmark does not vendor upstream hydrographic files. It uses a benchmark-local synthetic coastal grid, synthetic current field, and synthetic depth raster generated directly in `runtime/problem.py`.
- Authenticity note: the routing objective and minimum-depth constraint follow official HALEM lineage, while the environmental data is a frozen synthetic stand-in for offline reproducibility.
- Transformation path: no external preprocessing pipeline exists. All fields are generated from fixed formulas and constants inside the benchmark runtime.
