# Source Manifest

- Upstream lineage:
  - 52North `WeatherRoutingTool` repository and README
  - Fuel-aware ship routing under weather-dependent operating conditions
- License lineage: upstream code lineage is MIT.
- Data provenance: this benchmark does not redistribute upstream weather rasters. Instead it uses a benchmark-local synthetic coastal grid and deterministic wind/current fields generated directly in `runtime/problem.py`.
- Authenticity note: the optimization shape follows official weather-routing tool lineage, while the environment data is a frozen synthetic stand-in chosen for offline reproducibility.
- Transformation path: no external preprocessing pipeline exists. The map, land mask, current field, and wind field are generated from fixed formulas and constants inside the benchmark runtime.
