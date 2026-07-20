# ProteinDesign - 蛋白质设计

## 背景

蛋白质设计是生物工程的核心问题：给定一个目标结构（骨架），找到最稳定的氨基酸序列。本 benchmark 关注计算驱动的蛋白质序列设计优化。

本领域任务基于 "Protein Design with Agent Rosetta: A Case Study for Specialized Scientific Agents" (arXiv:2603.15952, ICML 2026)，使用 PyRosetta（Rosetta 的 Python 绑定）作为评分引擎。

## 任务列表

| 任务 | 描述 |
|------|------|
| [FixedBackboneDesign](FixedBackboneDesign/Task_zh-CN.md) | 固定骨架蛋白质序列设计优化 |

## 环境配置

本领域任务使用官方 Rosetta Docker 镜像运行评测，确保环境一致性。

```bash
docker pull rosettacommons/rosetta:serial
```

快捷运行命令：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ProteinDesign/FixedBackboneDesign \
  task.runtime.isolation_mode=docker \
  task.runtime.docker_image=rosettacommons/rosetta:serial \
  algorithm=openevolve \
  algorithm.iterations=0
```
