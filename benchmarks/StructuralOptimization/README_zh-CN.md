# 结构优化

本领域涵盖结构工程优化问题，包括由 [Bright Optimizer](http://www.brightoptimizer.com/) 组织的**国际结构优化学生竞赛（ISCSO）**衍生任务，以及公开发表的复合材料铺层与拓扑优化 benchmark。

结构优化是土木、航空航天和机械工程中的核心学科，目标是在满足安全约束（应力和位移限值）的条件下，找到使材料用量（重量）最小的承载结构最优设计。

## 任务列表

| 任务 | 描述 | 维度 | 类型 |
| :--- | :--- | :---: | :--- |
| `ISCSO2015` | 45 杆 2D 桁架尺寸 + 形状优化 | 54 | 连续、有约束、多工况 |
| `ISCSO2023` | 284 杆 3D 桁架尺寸优化 | 284 | 连续、有约束、多工况 |
| `TopologyOptimization` | MBB 束流二维拓扑优化 (SIMP) | 1200 | 连续、体积约束的合规最小化 |
| `PyMOTOSIMPCompliance` | 基于 pyMOTO 范式的二维梁 SIMP 柔度最小化拓扑设计 | 4800 | 连续、体积约束的合规最小化 |
| `CompositeLaminateStacking` | 跨板几何与载荷比例的平衡、对称 48 层铺层设计 | 120 | 离散、多工况、屈曲与失效约束 |

## 为何适合 Frontier-Engineering

| 特性 | ISCSO 2015 | ISCSO 2023 | 复合材料铺层 |
| :--- | :--- | :--- | :--- |
| 高维设计变量 | 中等 (54-D) | 高 (284-D) | 高（120 个整数变量） |
| 真实物理模型 | FEM | FEM | 经典层合板理论 + Ritz 屈曲分析 |
| 确定性评估 | 是 | 是 | 是 |
| 多工况约束 | 是 (2 工况) | 是 (3 工况) | 是（10 工况） |
| 非凸可行域 | 是 | 是 | 是 |
| 工业相关性 | 是 | 是 | 是 |

这些 benchmark 可作为：

- 黑盒约束优化 benchmark
- Agent + FEM 仿真交互 benchmark
- 自动算法设计 benchmark
- LLM + 数值仿真 benchmark

## 数据与运行环境

这些任务所需的 reference data 已随各任务的 `references/` 目录提交到仓库，不需要额外 asset bundle。unified 运行时请使用 `frontier-v1-main` 环境，例如：

```bash
python -m frontier_eval task=unified task.benchmark=StructuralOptimization/ISCSO2015 task.runtime.env_name=frontier-v1-main algorithm.iterations=0
```
