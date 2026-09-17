# Cybersecurity

本领域收集可执行的网络安全工程优化任务，强调明确的运行约束、风险敏感目标和由验证器独立重算的结果。

## 任务列表

- `DependencyAwarePatchScheduling`
  - `frontier_eval` 任务：`task=unified task.benchmark=Cybersecurity/DependencyAwarePatchScheduling`
  - 快速运行：`python -m frontier_eval task=unified task.benchmark=Cybersecurity/DependencyAwarePatchScheduling task.runtime.isolation_mode=process algorithm=openevolve algorithm.iterations=0`
  - 简介：在漏洞依赖、维护窗口、服务停机上限、可再生资源容量和回滚成本约束下进行风险感知的补丁选择与整数时隙调度。

该任务研究离线企业补丁规划。NIST SP 800-40 Rev. 4 和 CISA BOD 22-01
提供基于风险的规划和修复优先级背景；benchmark 中的金额参数和依赖图是合成数据，
并由冻结验证器独立重算。
