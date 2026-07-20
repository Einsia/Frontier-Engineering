# FixedBackboneDesign - 固定骨架蛋白质序列设计

## 概述

给定一个固定的蛋白质骨架（backbone），设计出最稳定的氨基酸序列。本任务对应 Agent Rosetta 论文（arXiv:2603.15952, ICML 2026）的 Case A：固定骨架规范氨基酸序列设计。

## 输入

candidate 脚本（`scripts/init.py`）接收以下参数：

- `--prepared-input`：包含目标骨架和设计位置标注的 PDB 文件路径
- `--solution-output`：设计结果 PDB 的输出路径

## 输出

candidate 必须在 `--solution-output` 输出一个 PDB 文件，包含：
1. 原始的骨架坐标（保持不变）
2. 在指定位置替换为设计后的氨基酸
3. 只能使用 20 种标准氨基酸（不允许非规范氨基酸）

## 评分方式

评估器使用 PyRosetta 的 `ref2015` 能量函数计算：

- **total_energy**：所有能量项的加和
- **baseline_energy**：初始序列的能量
- **improvement**：baseline_energy - total_energy（正数表示改进）
- **combined_score**：归一化改进值 = improvement / |baseline_energy|

报告的能量项：`fa_atr`、`fa_rep`、`fa_sol`、`fa_elec`、`hbond_bb_sc`、`hbond_sc`、`p_aa_pp`、`ref`

## 约束

- 只能修改 `scripts/init.py`
- 不得修改骨架坐标
- 只能使用 20 种标准氨基酸
- 输出必须是有效的 PDB 文件
