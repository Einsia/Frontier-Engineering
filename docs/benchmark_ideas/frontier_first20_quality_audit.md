# First 20 Benchmarks Quality Audit

Updated on 2026-03-13.

## Scope

This audit covers the first 20 benchmark ideas that were implemented under `benchmarks/`.

The quality gate used here follows the current `frontier-benchmark-contributor` skill:

1. Direct evaluator must return a finite score with `valid=1`.
2. Benchmark integrity must not leak hidden reference answers through agent-visible files.
3. Data provenance must be explicit and traceable.
4. `eval_single.sh` with 10 evolution steps is the second-line sanity check, but only when a working LLM credential is available in the current environment.

## Summary

- Direct evaluator pass rate: `20 / 20`
- Benchmarks with `valid=1.0`: `20 / 20`
- Reference-answer leakage fixed: `4 / 4`
- Inventory provenance manifests added: `5 / 5`
- Baseline/init scoring bias fixed: `DuckDBPreAggregationSelection`
- `eval_single.sh` 10-step sweep: blocked by current OpenRouter credential failure (`401 User not found`)

## Fixed Issues

### 1. Hidden reference solution leakage

The following tasks originally exposed full reference paths through agent-visible `runtime/problem.py` files. This is now fixed by keeping only scalar reference metrics in the public runtime.

- `OperationsResearch/FuelMinimizingShipWeatherRouting`
- `OperationsResearch/DynamicCurrentMinimumTimeRouting`
- `Robotics/GridPathPlanningWithObstacles`
- `Robotics/NarrowPassagePlanning`

### 2. Missing provenance manifests

The following tasks originally lacked `references/source_manifest.md`. Provenance files and source notes were added to task docs.

- `OperationsResearch/EOQWithMinimumOrderQuantity`
- `OperationsResearch/EOQWithAllUnitsDiscounts`
- `OperationsResearch/EOQWithIncrementalDiscounts`
- `OperationsResearch/PoissonRQServiceLevel`
- `OperationsResearch/NormalRQServiceLevel95`

### 3. Baseline-equivalence scoring bias

`ComputerSystems/DuckDBPreAggregationSelection` originally penalized the init candidate even when it matched the baseline design. The runtime helper now special-cases the no-preaggregation path so baseline-equivalent candidates score exactly `1.0`.

## Direct Evaluator Results

| Benchmark | Combined Score | Valid |
| --- | ---: | ---: |
| `OperationsResearch/EOQWithMinimumOrderQuantity` | `1.000000` | `1.0` |
| `OperationsResearch/EOQWithAllUnitsDiscounts` | `1.000000` | `1.0` |
| `OperationsResearch/EOQWithIncrementalDiscounts` | `1.000000` | `1.0` |
| `OperationsResearch/PoissonRQServiceLevel` | `1.000000` | `1.0` |
| `OperationsResearch/NormalRQServiceLevel95` | `1.000000` | `1.0` |
| `OperationsResearch/FT10DispatchingRuleOptimization` | `0.865922` | `1.0` |
| `OperationsResearch/LA16DispatchingRuleOptimization` | `0.747036` | `1.0` |
| `OperationsResearch/FT10NeighborhoodMoveSelection` | `0.914454` | `1.0` |
| `OperationsResearch/LA16NeighborhoodMoveSelection` | `0.859873` | `1.0` |
| `ComputerSystems/DuckDBIndexSelection` | `0.998004` | `1.0` |
| `ComputerSystems/DuckDBQueryRewrite` | `1.000472` | `1.0` |
| `ComputerSystems/DuckDBPreAggregationSelection` | `1.000000` | `1.0` |
| `Robotics/GridPathPlanningWithObstacles` | `0.875000` | `1.0` |
| `Robotics/NarrowPassagePlanning` | `0.944444` | `1.0` |
| `Robotics/MultiRobotPrioritizedPlanning` | `1.000000` | `1.0` |
| `StructuralOptimization/CantileverComplianceTopologyOptimization` | `1.000000` | `1.0` |
| `StructuralOptimization/MBBBeamTopologyOptimization` | `1.000000` | `1.0` |
| `StructuralOptimization/BridgeTopologyOptimization` | `1.000000` | `1.0` |
| `OperationsResearch/FuelMinimizingShipWeatherRouting` | `0.402275` | `1.0` |
| `OperationsResearch/DynamicCurrentMinimumTimeRouting` | `0.619596` | `1.0` |

## `eval_single.sh` Status

Attempted command shape:

```bash
PYTHON_BIN=/mnt/shared-storage-user/p1-shared/luotianwei/Frontier-Engineering/.venv/bin/python \
./eval_single.sh \
  task=unified \
  task.benchmark=OperationsResearch/EOQWithMinimumOrderQuantity \
  task.runtime.use_conda_run=false \
  task.runtime.python_path=/mnt/shared-storage-user/p1-shared/luotianwei/Frontier-Engineering/.venv/bin/python
```

Observed blocker:

- The run starts correctly.
- `frontier_eval` loads `.env`.
- The configured provider is `https://openrouter.ai/api/v1`.
- Candidate generation fails immediately with `401 User not found`.

Because of that provider-side auth failure, the 10-step improvement check cannot be used as a benchmark quality signal in the current shell yet.

## Current Conclusion

The first 20 benchmarks now pass the structural quality gate:

- They produce valid direct-evaluator scores.
- The identified answer-leakage issue has been removed.
- Provenance coverage is materially better.
- Known scoring asymmetry in DuckDB pre-aggregation is fixed.

The remaining open gate is operational rather than benchmark-specific:

- restore a working LLM credential for `frontier_eval`
- then run `eval_single.sh` across the 20 tasks
- then record which tasks show reliable improvement signal within 10 steps
