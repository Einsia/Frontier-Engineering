# Agent-Evolve 量子题目集

本目录包含 4 个优化题目。题目 01–03 优化电路，基于本仓库的 `mqt.bench` API；题目 04 是
量子纠错码的经典解码器，不使用 `mqt.bench`。

## 环境

题目 01–03 请使用指定解释器：

```bash
pip install mqt.bench
```

题目 04 需要自己的评测端依赖（Stim + PyMatching），见
`task_04_quantum_error_decoder/README_zh-CN.md`。

## 题目列表
- `task_01_routing_qftentangled`：面向 IBM Falcon 的 mapped-level 路由优化。
- `task_02_clifford_t_synthesis`：面向 `clifford+t` 原生门集的综合优化。
- `task_03_cross_target_qaoa`：同一策略在 IBM 与 IonQ 双目标上的鲁棒优化。
- `task_04_quantum_error_decoder`：表面码解码器，以最小权完美匹配为基准（逻辑错误率，
  超过基准不封顶）。

当前 baseline 策略：
- `task_01`：先做 local rewrite，再做面向 target 的多 seed transpile 搜索。
- `task_02`：`local rewrite -> clifford+t transpile(opt=3) -> local rewrite`。
- `task_03`：按后端注册 equivalence，并使用 target-aware transpile 参数。
- `task_04`：永不预测逻辑翻转（合法，且按构造得 0.0 分）。

## 统一目录结构
每个题目都采用同一结构：
- `baseline/solve.py`：包含各题目当前 baseline 策略的 evolve 入口。
- `baseline/structural_optimizer.py`：由 `solve.py` 复用的 task-local local-rewrite 辅助模块（题目 01–03）。
- `verification/evaluate.py`：单一评测入口。
- `verification/utils.py`：公共工具函数（题目 01–03）。
- `tests/case_*.json`：多个有差异的测例（题目 01–03）。
- `README*.md` 与 `TASK*.md`：运行说明与任务定义。

题目 04 额外提供 `verification/candidate_runner.py`，它在独立解释器中加载 candidate 解码器，
该进程永远不会收到真实的观测量翻转。

## 评测命令
```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_01_routing_qftentangled task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_02_clifford_t_synthesis task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_03_cross_target_qaoa task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_04_quantum_error_decoder task.runtime.env_name=frontier-v1-main algorithm=openevolve algorithm.iterations=0
```