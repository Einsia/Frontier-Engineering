# 通信工程 (CommunicationEngineering)

本领域专注于通信系统中的优化问题，包括资源分配、信号处理和网络优化。这些问题对现代无线和有线通信系统至关重要，直接影响系统性能、能源效率和用户体验。

## 领域概述

通信工程任务涉及优化通信系统的各个方面：

1. **资源分配**：优化有限资源（频率、时间、功率）在多个用户或服务之间的分配，以最大化系统效率。
2. **信号处理**：优化信号处理算法（如预编码、波束成形）以提高通信质量和可靠性。
3. **网络优化**：优化通信网络中的路由、调度和资源管理，以最小化延迟并最大化吞吐量。

## 问题特征

- **现实约束**：物理限制（功率预算、带宽约束、干扰）
- **多目标优化**：通常需要平衡吞吐量、能源效率、公平性和服务质量
- **动态环境**：信道条件、流量模式和网络拓扑可能变化
- **可扩展性**：解决方案必须在大规模系统中高效工作

## 子任务索引

- `AdaptiveLinkScheduling/`: 在队列、信道、时延、公平性与功率预算约束下优化下行资源块调度、MCS 选择和发射功率。
  - `frontier_eval` 任务: `task=unified task.benchmark=CommunicationEngineering/AdaptiveLinkScheduling`
  - 快速运行: `python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/AdaptiveLinkScheduling algorithm.iterations=0`

- `LDPCErrorFloor/`: 使用重要性采样估计LDPC码的错误地板，处理罕见的trapping set事件。
  - `frontier_eval` 任务: `task=unified task.benchmark=CommunicationEngineering/LDPCErrorFloor`
  - 快速运行: `python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/LDPCErrorFloor algorithm.iterations=0`

- `RayleighFadingBER/`: 使用重要性采样分析瑞利衰落信道下的误码率，模拟深衰落事件。
  - `frontier_eval` 任务: `task=unified task.benchmark=CommunicationEngineering/RayleighFadingBER`
  - 快速运行: `python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/RayleighFadingBER algorithm.iterations=0`

- `PMDSimulation/`: 使用重要性采样仿真光纤系统中的极化模色散(PMD)，处理罕见的停机事件。
  - `frontier_eval` 任务: `task=unified task.benchmark=CommunicationEngineering/PMDSimulation`
  - 快速运行: `python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/PMDSimulation algorithm.iterations=0`
