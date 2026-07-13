# PowerSystems

This domain collects engineering optimization tasks for electric power systems and energy infrastructure.
Current tasks emphasize realistic operational constraints, economic objectives, and executable verification.

## Tasks

- `EV2GymSmartCharging`
  - Unified benchmark: `task=unified task.benchmark=PowerSystems/EV2GymSmartCharging`
  - Quick run: `python -m frontier_eval task=unified task.benchmark=PowerSystems/EV2GymSmartCharging task.runtime.env_name=frontier-eval-driver algorithm.iterations=0`
  - Description: upstream-aligned EV smart charging with transformer constraints in the real `EV2Gym` simulator

- `MicrogridBatteryDispatch`
  - Unified benchmark: `task=unified task.benchmark=PowerSystems/MicrogridBatteryDispatch`
  - Quick run: `python -m frontier_eval task=unified task.benchmark=PowerSystems/MicrogridBatteryDispatch algorithm.iterations=0`
  - Description: battery dispatch for a solar commercial microgrid under tariffs, demand charges, degradation, and physical limits
