# FixedBackboneDesign - 固定骨架蛋白质序列设计

## 一句话解释

给定一个蛋白质的骨架结构（backbone），设计出最适合这个骨架的氨基酸序列，使 Rosetta 能量得分最低。

## 任务描述

本任务基于 Agent Rosetta 论文 (arXiv:2603.15952) 的 Case A：固定骨架规范氨基酸序列设计。Agent 需要从初始 baseline 出发，通过迭代优化找到总能量更低的氨基酸序列。

## 文件结构

```
FixedBackboneDesign/
├── Task.md                      # 任务详情（英文）
├── Task_zh-CN.md                # 任务详情（中文）
├── README.md                    # 本文件（导航）
├── scripts/
│   └── init.py                  # [可编辑] baseline 解法（含 EVOLVE-BLOCK）
├── data/
│   └── raw_task.json            # 任务配置
├── references/
│   ├── constants.json           # Rosetta 能量函数参数
│   └── petrobind/               # PDB 结构文件
├── frontier_eval/               # unified task 元数据
├── verification/
│   ├── evaluator.py             # [核心] PyRosetta 评分入口
│   ├── requirements.txt
│   └── docker/
│       └── Dockerfile
└── baseline/                    # [可选] 参考实现存档
```

## 运行方式

### 本地三步运行

```bash
cd benchmarks/ProteinDesign/FixedBackboneDesign
mkdir -p outputs

# 1. prepare（由 evaluator 完成数据准备）
python verification/evaluator.py prepare \
  --raw-task data/raw_task.json \
  --prepared-output outputs/prepared.pdb

# 2. 运行 baseline 生成设计结果
python scripts/init.py \
  --prepared-input outputs/prepared.pdb \
  --solution-output outputs/solution.pdb

# 3. 评估设计结果
python verification/evaluator.py evaluate \
  --native outputs/prepared.pdb \
  --candidate outputs/solution.pdb \
  --result-output outputs/result.json
```

### Unified task 方式

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ProteinDesign/FixedBackboneDesign \
  task.runtime.isolation_mode=docker \
  task.runtime.docker_image=rosettacommons/rosetta:serial \
  algorithm=openevolve \
  algorithm.iterations=0
```

## 统一 benchmark ID

- `ProteinDesign/FixedBackboneDesign`

## 环境准备

本任务需要 Rosetta 环境，推荐使用官方 Docker 镜像：

```bash
docker pull rosettacommons/rosetta:serial
```
