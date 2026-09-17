# Robotics

This domain contains robotics control and planning tasks for unified evaluation.

## Tasks

- `CoFlyersVasarhelyiTuning`
  - Unified benchmark: `task=coflyers_vasarhelyi_tuning`
  - Quick run: `python -m frontier_eval task=coflyers_vasarhelyi_tuning algorithm.iterations=0`
- `DynamicObstacleAvoidanceNavigation`
- `PIDTuning`
- `QuadrupedGaitOptimization`
- `RobotArmCycleTimeOptimization`
- `UAVInspectionCoverageWithWind`
- `WarehouseRobotRouting`

### Unified quick runs

- `DynamicObstacleAvoidanceNavigation`: `python -m frontier_eval task=unified task.benchmark=Robotics/DynamicObstacleAvoidanceNavigation algorithm.iterations=0`
- `PIDTuning`: `python -m frontier_eval task=unified task.benchmark=Robotics/PIDTuning algorithm.iterations=0`
- `QuadrupedGaitOptimization`: `.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=Robotics/QuadrupedGaitOptimization task.runtime.env_name=frontier-v1-main algorithm.iterations=0`
- `RobotArmCycleTimeOptimization`: `.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=Robotics/RobotArmCycleTimeOptimization task.runtime.env_name=frontier-v1-main algorithm.iterations=0`
- `UAVInspectionCoverageWithWind`: `python -m frontier_eval task=unified task.benchmark=Robotics/UAVInspectionCoverageWithWind algorithm.iterations=0`
- `WarehouseRobotRouting`: `python -m frontier_eval task=unified task.benchmark=Robotics/WarehouseRobotRouting task.runtime.isolation_mode=process algorithm=openevolve algorithm.iterations=0`
