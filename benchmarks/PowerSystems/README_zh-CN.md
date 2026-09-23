# PowerSystems

本域收集电力系统与能源基础设施相关的工程优化任务。
当前任务强调真实运行约束、经济目标以及可执行验证。

## 任务列表

- `EV2GymSmartCharging`
  - `frontier_eval` 任务：`task=unified task.benchmark=PowerSystems/EV2GymSmartCharging`
  - 快速运行：`python -m frontier_eval task=unified task.benchmark=PowerSystems/EV2GymSmartCharging task.runtime.env_name=frontier-eval-driver algorithm.iterations=0`
  - 简介：在真实上游 `EV2Gym` 模拟器中进行、与上游数据对齐的 EV 智能充电与变压器约束优化
- `TelecomBackup`
  - `frontier_eval` 任务：`task=unified task.benchmark=PowerSystems/TelecomBackup`
  - 快速运行（官方评测用运行时生成实例，必须提供非公开种子；已抬高超时以容纳完整每实例预算）：`TELECOM_EVAL_GENERATE_SEED=<SEED> python -m frontier_eval task=unified task.benchmark=PowerSystems/TelecomBackup algorithm.iterations=0 algorithm.evaluator.timeout=1200`
  - 简介：电信备电电源的时序开关调度，在停电时最大化备电时长同时保持 LTE 覆盖 ≥ 80%
