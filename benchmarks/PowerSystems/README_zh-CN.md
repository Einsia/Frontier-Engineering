# PowerSystems

本域收集电力系统与能源基础设施相关的工程优化任务。
当前任务强调真实运行约束、经济目标以及可执行验证。

## 任务列表

- `EV2GymSmartCharging`
  - `frontier_eval` 任务：`task=unified task.benchmark=PowerSystems/EV2GymSmartCharging`
  - 快速运行：`python -m frontier_eval task=unified task.benchmark=PowerSystems/EV2GymSmartCharging task.runtime.env_name=frontier-eval-driver algorithm.iterations=0`
  - 简介：在真实上游 `EV2Gym` 模拟器中进行、与上游数据对齐的 EV 智能充电与变压器约束优化

- `SecurityConstrainedDispatch`
  - `frontier_eval` 任务：`task=unified task.benchmark=PowerSystems/SecurityConstrainedDispatch`
  - 运行环境：安装 `verification/requirements.txt` 中的固定依赖，并通过 `task.runtime.python_path` 指定解释器
  - 简介：在正常与 N-1 PGLib 场景中优化成本和安全裕度，并由冻结交流潮流验证器评分
