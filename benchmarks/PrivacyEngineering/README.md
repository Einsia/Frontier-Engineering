# Privacy Engineering

This domain collects executable privacy-engineering optimization tasks with explicit
privacy-loss budgets, utility objectives, policy constraints, and independently
recomputed verification.

## Tasks

- `DifferentialPrivacyBudgetAllocation`
  - Unified benchmark: `task=unified task.benchmark=PrivacyEngineering/DifferentialPrivacyBudgetAllocation`
  - Quick run: `python -m frontier_eval task=unified task.benchmark=PrivacyEngineering/DifferentialPrivacyBudgetAllocation task.runtime.isolation_mode=process algorithm=openevolve algorithm.iterations=0`
  - Description: allocate a fixed differential-privacy budget across analytics queries with heterogeneous sensitivity, business value, population coverage, fairness requirements, and estimation-accuracy constraints.

The task models offline privacy-budget planning for business analytics portfolios.
NIST SP 800-226 and Dwork and Roth's differential privacy text provide the privacy
parameter, privacy loss, sensitivity, and utility-tradeoff context; the benchmark
instances are synthetic and are recomputed by the frozen verifier.
