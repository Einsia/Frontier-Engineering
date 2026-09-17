# Cybersecurity

This domain collects executable cybersecurity engineering optimization tasks with
explicit operational constraints, risk-sensitive objectives, and independently
recomputed verification.

## Tasks

- `DependencyAwarePatchScheduling`
  - Unified benchmark: `task=unified task.benchmark=Cybersecurity/DependencyAwarePatchScheduling`
  - Quick run: `python -m frontier_eval task=unified task.benchmark=Cybersecurity/DependencyAwarePatchScheduling task.runtime.isolation_mode=process algorithm=openevolve algorithm.iterations=0`
  - Description: risk-based patch selection and integer-slot scheduling under vulnerability dependencies, maintenance windows, service downtime limits, renewable resource capacities, and rollback costs.

The task models offline enterprise patch planning. NIST SP 800-40 Rev. 4 and CISA
BOD 22-01 provide the risk-based planning and remediation-priority context; the
benchmark's monetary parameters and generated dependency graphs are synthetic and
are recomputed by the frozen verifier.
