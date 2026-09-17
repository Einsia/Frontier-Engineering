# EdgeServiceReplicaPlacement

这是一个 CPU-only、确定性的 edge service 副本放置与流量路由 benchmark。候选实现
动态策略，而不是一次性 allocation：

```python
def decide(observation: dict) -> dict:
    ...
```

Evaluator 在 10 个、每个 24 时段的场景中运行策略，覆盖正常日内负载、区域突发、节点
故障叠加突发、跨区链路降级和故障恢复后的流量迁移。扩容有一个时段 cold start。
Simulator 独立计算 availability、P95/P99 估计、SLA 违规、计算成本、跨区流量/成本和
恢复时长。

## 直接验证

在当前目录运行：

```bash
python verification/evaluator.py scripts/init.py \
  --metrics-out metrics.json --artifacts-out artifacts.json
python -m unittest discover -s verification -p "test_*.py" -v
```

## Unified 零迭代验证

在仓库根目录运行：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/EdgeServiceReplicaPlacement \
  algorithm=openevolve \
  algorithm.iterations=0
```

## 可编辑边界

Agent 只能修改 `scripts/init.py` 中的 EVOLVE-BLOCK。Worker 接收 JSON observation 并返回
JSON action；每个 scenario 使用新的临时进程，并限制决定时间和输出大小。该进程边界可
避免一般的共享状态和协议耦合，但不能替代操作系统级安全沙箱。

接口见 [Task_zh-CN.md](Task_zh-CN.md)，模型假设见
[references/design_notes.md](references/design_notes.md)。
