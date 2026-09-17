# 量子计算基准

本目录包含量子电路构造、综合、路由与跨目标优化任务。

## 题目列表

- [`KernelBlockEncoding`](KernelBlockEncoding/)：为定点 QML 核矩阵构造兼顾归一化与资源的 FABLE 电路；评测器自包含且仅使用 CPU。
- `task_01_routing_qftentangled`：面向 IBM Falcon 的 mapped-level 路由优化。
- `task_02_clifford_t_synthesis`：面向 `clifford+t` 原生门集的综合优化。
- `task_03_cross_target_qaoa`：同一策略在 IBM 与 IonQ 双目标上的鲁棒优化。

三个历史 `task_0*` 任务使用本仓库的 `mqt.bench` API，需要已配置的量子环境。`KernelBlockEncoding` 只需 Python 3 与 C++17 编译器，不需量子 SDK 或模拟器。

## 历史 MQT 任务结构

MQT 任务的当前 baseline 策略：

- `task_01`：先做 local rewrite，再做面向 target 的多 seed transpile 搜索。
- `task_02`：`local rewrite -> clifford+t transpile(opt=3) -> local rewrite`。
- `task_03`：按后端注册 equivalence，并使用 target-aware transpile 参数。

每个历史题目都采用以下结构：

- `baseline/solve.py`：包含各题目当前 baseline 策略的 evolve 入口。
- `baseline/structural_optimizer.py`：由 `solve.py` 复用的 task-local local-rewrite 辅助模块。
- `verification/evaluate.py`：单一评测入口，同时包含 candidate 与 `opt0..opt3` 参考对比。
- `verification/utils.py`：公共工具函数。
- `tests/case_*.json`：多个有差异的测例。
- `README*.md` 与 `TASK*.md`：运行说明与任务定义。

## 评测命令

核矩阵分块编码：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/KernelBlockEncoding algorithm=openevolve algorithm.iterations=0
```

MQT 任务：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_01_routing_qftentangled task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_02_clifford_t_synthesis task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_03_cross_target_qaoa task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
```
