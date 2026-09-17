# First 20 Ideas Implementation Status

Updated on 2026-03-13.

See also: `docs/benchmark_ideas/frontier_first20_quality_audit.md` for the consolidated integrity and scoring audit across these tasks.

## Implemented and Smoke-Tested

These benchmarks have been created and passed direct evaluator runs. `EOQWithMinimumOrderQuantity`, `CantileverComplianceTopologyOptimization`, `MultiRobotPrioritizedPlanning`, `DuckDBQueryRewrite`, and `FuelMinimizingShipWeatherRouting` also passed `frontier_eval task=unified` smoke runs when forced to use the repository `.venv` Python.

Under `benchmarks/OperationsResearch/`:

1. `EOQWithMinimumOrderQuantity`
2. `EOQWithAllUnitsDiscounts`
3. `EOQWithIncrementalDiscounts`
4. `PoissonRQServiceLevel`
5. `NormalRQServiceLevel95`
6. `FT10DispatchingRuleOptimization`
7. `LA16DispatchingRuleOptimization`
8. `FT10NeighborhoodMoveSelection`
9. `LA16NeighborhoodMoveSelection`
19. `FuelMinimizingShipWeatherRouting`
20. `DynamicCurrentMinimumTimeRouting`

Under `benchmarks/StructuralOptimization/`:

16. `CantileverComplianceTopologyOptimization`
17. `MBBBeamTopologyOptimization`
18. `BridgeTopologyOptimization`

Under `benchmarks/Robotics/`:

13. `GridPathPlanningWithObstacles`
14. `NarrowPassagePlanning`
15. `MultiRobotPrioritizedPlanning`

Under `benchmarks/ComputerSystems/`:

10. `DuckDBIndexSelection`
11. `DuckDBQueryRewrite`
12. `DuckDBPreAggregationSelection`

Notes:

- JSSP benchmark instance data has been cloned from `job_shop_lib` into `/tmp/job_shop_lib`, and the canonical JSON payload is available locally.
- `pymoto` is installed in the repository `.venv`.
- `duckdb` is installed in the repository `.venv`.
- The DuckDB benchmarks intentionally use a benchmark-local deterministic SQL-generated workload with DuckDB/TPC-H schema lineage. They do not claim to redistribute official `dbgen` output.
- The maritime routing benchmarks intentionally use benchmark-local synthetic coastal fields with official WeatherRoutingTool / HALEM algorithm lineage. They do not claim to redistribute official hydrographic or weather rasters.
