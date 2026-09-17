# PowerSystems

本域收集电力系统与能源基础设施相关的工程优化任务。
当前任务强调真实运行约束、经济目标以及可执行验证。

## 任务列表

- `EV2GymSmartCharging`
  - `frontier_eval` 任务：`task=unified task.benchmark=PowerSystems/EV2GymSmartCharging`
  - 快速运行：`python -m frontier_eval task=unified task.benchmark=PowerSystems/EV2GymSmartCharging task.runtime.env_name=frontier-eval-driver algorithm.iterations=0`
  - 简介：在真实上游 `EV2Gym` 模拟器中进行、与上游数据对齐的 EV 智能充电与变压器约束优化

- `MicrogridBatteryDispatch`
  - `frontier_eval` 任务：`task=unified task.benchmark=PowerSystems/MicrogridBatteryDispatch`
  - 快速运行：`python -m frontier_eval task=unified task.benchmark=PowerSystems/MicrogridBatteryDispatch algorithm.iterations=0`
  - 简介：在分时电价、需量电费、电池退化和物理功率约束下优化商业微电网电池调度
