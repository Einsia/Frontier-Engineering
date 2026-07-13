# 风电场尾流偏航控制

本任务要求 Agent 优化一个确定性的偏航控制策略。冻结的 FLORIS 4.6.6
验证器在多种风向和风速下评估九台风机组成的风电场。

## 目录

```text
scripts/init.py                 可编辑偏航策略
references/farm_config.json     公开风场与评分契约
verification/evaluator.py       冻结的 FLORIS 验证器
verification/run_candidate.py   候选代码隔离运行器
frontier_eval/                  unified-task 元数据
baseline/result_log.json        零偏航基线结果
```

## 环境

在 Frontier-Engineering 仓库根目录执行：

```bash
python -m venv .venvs/frontier-wake-steering
.venvs/frontier-wake-steering/bin/python -m pip install \
  -r benchmarks/WindEnergy/WakeSteeringControl/verification/requirements.txt
```

本任务仅需 CPU，FLORIS 不要求 GPU。

## 直接评测

在任务目录中执行：

```bash
../../../.venvs/frontier-wake-steering/bin/python \
  verification/evaluator.py scripts/init.py
```

验证器生成 `metrics.json` 和 `artifacts.json`。仓库自带的零偏航策略保证可行，
其综合分数按定义约为零。

## Unified 评测

任务 ID 为 `WindEnergy/WakeSteeringControl`：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=WindEnergy/WakeSteeringControl \
  task.runtime.python_path=uv-env:frontier-wake-steering \
  algorithm=openevolve \
  algorithm.iterations=0
```

零迭代验证不需要模型 API Key；正式优化使用 Frontier Eval 的常规模型配置。

## 复现与安全

- FLORIS 固定为 4.6.6。
- 验证器使用内置 NREL 5 MW 风机和固定风场。
- 候选代码在带超时的独立子进程中运行。
- unified task 检查验证器与公开契约是否保持只读，修改这些文件的候选会被判为无效。
- 进程隔离不是强安全沙箱；不可信候选应在容器或一次性主机中运行。
