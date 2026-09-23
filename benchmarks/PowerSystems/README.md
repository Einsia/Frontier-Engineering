# PowerSystems

This domain collects engineering optimization tasks for electric power systems and energy infrastructure.
Current tasks emphasize realistic operational constraints, economic objectives, and executable verification.

## Tasks

- `EV2GymSmartCharging`
  - Unified benchmark: `task=unified task.benchmark=PowerSystems/EV2GymSmartCharging`
  - Quick run: `python -m frontier_eval task=unified task.benchmark=PowerSystems/EV2GymSmartCharging task.runtime.env_name=frontier-eval-driver algorithm.iterations=0`
  - Description: upstream-aligned EV smart charging with transformer constraints in the real `EV2Gym` simulator
- `TelecomBackup`
  - Unified benchmark: `task=unified task.benchmark=PowerSystems/TelecomBackup`
  - Quick run (official scoring uses generated instances and requires a non-public seed; the timeout is raised so the full per-instance budget fits): `TELECOM_EVAL_GENERATE_SEED=<SEED> python -m frontier_eval task=unified task.benchmark=PowerSystems/TelecomBackup algorithm.iterations=0 algorithm.evaluator.timeout=1200`
  - Description: time-sequenced on/off scheduling of telecom backup power supplies to maximize outage backup time while keeping LTE coverage >= 80%
