# Privacy Engineering

本领域收集可执行的隐私工程优化任务，强调明确的隐私损失预算、效用目标、策略约束和由验证器独立重算的结果。

## 任务列表

- `DifferentialPrivacyBudgetAllocation`
  - `frontier_eval` 任务：`task=unified task.benchmark=PrivacyEngineering/DifferentialPrivacyBudgetAllocation`
  - 快速运行：`python -m frontier_eval task=unified task.benchmark=PrivacyEngineering/DifferentialPrivacyBudgetAllocation task.runtime.isolation_mode=process algorithm=openevolve algorithm.iterations=0`
  - 简介：在查询敏感度、业务价值、覆盖人群、公平性要求和估计精度约束不同的情况下，为一组分析查询分配固定的差分隐私预算。

该任务研究离线业务分析组合中的隐私预算规划。NIST SP 800-226 以及 Dwork 和 Roth
的差分隐私教材提供隐私参数、隐私损失、敏感度和效用权衡背景；benchmark 实例是合成数据，
并由冻结验证器独立重算。
