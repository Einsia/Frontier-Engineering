# PowerSystems

This domain collects engineering optimization tasks for electric power systems and energy infrastructure.
Current tasks emphasize realistic operational constraints, economic objectives, and executable verification.

## Tasks

- `EV2GymSmartCharging`
  - Unified benchmark: `task=unified task.benchmark=PowerSystems/EV2GymSmartCharging`
  - Quick run: `python -m frontier_eval task=unified task.benchmark=PowerSystems/EV2GymSmartCharging task.runtime.env_name=frontier-eval-driver algorithm.iterations=0`
  - Description: upstream-aligned EV smart charging with transformer constraints in the real `EV2Gym` simulator

- `SecurityConstrainedDispatch`
  - Unified benchmark: `task=unified task.benchmark=PowerSystems/SecurityConstrainedDispatch`
  - Runtime: install the pinned packages in `verification/requirements.txt` and set `task.runtime.python_path` to that environment
  - Description: cost-and-security dispatch across normal and N-1 PGLib operating scenarios with frozen AC power-flow verification
