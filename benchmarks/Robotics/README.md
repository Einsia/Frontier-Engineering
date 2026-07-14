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

### Unified quick runs

- `DynamicObstacleAvoidanceNavigation`: `python -m frontier_eval task=unified task.benchmark=Robotics/DynamicObstacleAvoidanceNavigation algorithm.iterations=0`
- `PIDTuning`: `python -m frontier_eval task=unified task.benchmark=Robotics/PIDTuning algorithm.iterations=0`
- `QuadrupedGaitOptimization`: `.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=Robotics/QuadrupedGaitOptimization task.runtime.env_name=frontier-v1-main algorithm.iterations=0`
- `RobotArmCycleTimeOptimization`: `.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=Robotics/RobotArmCycleTimeOptimization task.runtime.env_name=frontier-v1-main algorithm.iterations=0`
- `UAVInspectionCoverageWithWind`: `python -m frontier_eval task=unified task.benchmark=Robotics/UAVInspectionCoverageWithWind algorithm.iterations=0`

## Benchgen Tasks

<!-- BENCHGEN-TASK-INDEX-START -->
- [WarehouseRobotRouting](WarehouseRobotRouting/README.md): 带碰撞与载重约束的多仓储机器人路径规划 - 给定离散仓库通行图、机器人初始位置、载重上限、规划时域，以及包含取货点、送货点和货物重量的订单，参赛系统输出每台机器人的逐时刻路径与取送货动作。实例覆盖不同仓库布局、机器人密度、订单规模和拥堵程度，并以全部订单完成后的机器人总移动距离衡量方案质量。
<!-- BENCHGEN-TASK-INDEX-END -->
