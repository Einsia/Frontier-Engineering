# FPGA 布局优化（FPGA Placement Optimization）

将数字逻辑实例（LUT、FF、DSP、BRAM、carry chain）分配到 FPGA 器件上的合法站点，在满足所有 FPGA 特定合法性约束的前提下最小化线长（wirelength）。

本 benchmark 基于 **ISPD 2016 FPGA Placement Contest** 基准测试集。

## 设计理念（Benchmark Philosophy）

本 benchmark 评估 AI agent **设计并迭代改进 FPGA 布局算法（placement algorithm）** 的能力。FPGA 布局是经典电子设计自动化（Electronic Design Automation, EDA）问题，具有真实的工程约束：布局必须完全合法（legal）方可使用，线长直接影响电路时序、功耗和可布线能力。

可编辑组件（editable artifact, scripts/init.py）被有意设计为一个**轻量级可运行实现**——一个朴素的逐行扫描布局器（row-scan placer），仅使用 Python 标准库即可生成合法但线长较高的布局。这一设计选择基于两个目的：

- 提供**明确的改进起点**，而非要求 agent 调整已高度优化的工业布局器。
- 保持**低入门门槛**：agent 可专注于布局算法设计，无需管理外部依赖、GPU 工具链或专有框架。

本 benchmark **并非**为进化或调优现有生产级 FPGA 布局器（如 aug-elfPlace 或 DreamPlaceFPGA）而设计。这些系统代表了多年的工程积累，更适合作为参考材料。相反，本 benchmark 鼓励 agent **从可行起点出发设计布局策略**，在尊重 benchmark 接口的前提下拥有完全替换算法的自由。

评测器（evaluator）在候选算法与评分流水线之间实施严格分离：它运行候选程序、检查合法性并计算半周长线长（Half-Perimeter Wirelength, HPWL）——所有这些均独立于候选程序的内部实现。这意味着 agent 可以使用解析布局（analytical placement）、模拟退火（simulated annealing）、构造启发式或机器学习等方法，只要输出结果合法且线长最小，评测器将一视同仁。

## Agent 任务（Agent Task）

**可编辑组件** 是 scripts/init.py。

该文件实现了一个轻量级、确定性的逐行扫描布局器，能够生成合法但线长较高的布局。其设计有意保持简单：

- 仅使用 **Python 标准库**——无外部依赖。
- **不是** aug-elfPlace、DreamPlaceFPGA 或其他生产布局器的包装。
- 是一个**起始点**——一个可行但次优的布局，agent 应在此基础上重新设计并改进。

agent 拥有**完全自由**来重新设计布局算法。唯一约束是：

1. 程序必须接受相同的命令行接口（--nodes, --pl, --scl, --output）。
2. 程序必须按相同格式输出 solution.pl。
3. 布局必须满足三个合法性门（G1, G2, G3）。

scripts/init.py 中 EVOLVE-BLOCK 内的所有内容——包括解析器、数据结构和布局策略——均可修改、替换或删除。

## 基线（Baseline）

aseline/ 目录包含与初始求解器相同的逐行扫描实现，作为**人工比较的参考分数**。Agent 不修改基线。评测器从不将候选输出与基线比较；它独立评分候选输出。

## 评测流程（Evaluation）

评测器（erification/evaluator.py）按以下步骤评分候选程序：

1. 运行候选程序（scripts/init.py）生成 solution.pl。
2. 使用独立的 NumPy 实现计算 **HPWL**（半周长线长）。
3. 检查 **硬性验证门**：站点类型兼容性（G1）、资源容量（G2）、进位链完整性（G3）。
4. 返回 combined_score = -HPWL（合法布局）或 combined_score = -1e18（非法布局）。

评测器**独立于**候选程序。它不与环境基线比较，仅评分候选输出。

## 默认 Benchmark

评测器默认使用 **fpga-example1** 设计（
eferences/design.*）。这是有意的设计选择：

- **快速评测**：Frontier-Agent 在进化过程中会执行大量评测迭代。轻量级 benchmark（约 1 MB，约 3000 个实例）将每次迭代时间控制在 1 秒以内，支持快速实验。
- **确定性基准**：小规模设计便于验证正确性和调试布局算法。
- **足够复杂度**：尽管规模小，fpga-example1 可同时检验三种合法性门（SLICE/DSP/BRAM 站点类型、资源容量、进位链），并产出有意义的 HPWL 比较。

评测器通过 --benchmark 参数支持完整的 **ISPD 2016 benchmark 套件**：

`
# 针对特定 ISPD 2016 设计进行评测：
python verification/evaluator.py scripts/init.py --benchmark FPGA01

# 可用设计：FPGA01 .. FPGA12
`

ISPD 2016 benchmark（
eferences/ispd2016/）可用于扩展评测。这些更大规模的设计（总计约 166 MB，单个设计最多 15 万个实例）适合在布局算法稳定后进行最终验证。

## 文件结构（File Structure）

`
FPGAPlacementOptimization/
├── README.md                                     导航文档（本文件）
├── README_zh-CN.md                               中文版导航文档
├── Task.md                                       核心任务契约
├── Task_zh-CN.md                                 中文版任务契约
├── references/                                   Benchmark 数据集（只读）
│   ├── design.*                                  fpga-example1（默认 benchmark）
│   └── ispd2016/                                 ISPD 2016 套件（单独下载，参见数据集配置）
├── baseline/                                     参考基线（row-scan placer）
│   ├── solution.py                               参考实现
│   └── result_log.txt                            预期结果
├── scripts/
│   └── init.py                                   可编辑布局器入口点
├── verification/
│   ├── canonical.py                              参考解析器、HPWL、合法性门
│   ├── evaluator.py                              冻结的评分流水线
│   └── requirements.txt                          依赖项（numpy）
├── frontier_eval/                                统一任务元数据
├── ClockAwarePlacement_Design_Report.md          设计探索（存档）
└── ClockAwarePlacement_DesignValidation.md       设计验证（存档）
`

## 快速开始（Quick Start）

### 1. 安装依赖

`
pip install numpy scipy
`

### 2. 运行初始求解器

`
cd benchmarks/FPGA/FPGAPlacementOptimization
python scripts/init.py
# 生成：solution.pl
# 预期：HPWL ~210721，所有合法性门通过
`

### 3. 评测候选方案

默认 benchmark（fpga-example1）：

`
python verification/evaluator.py scripts/init.py
`

针对 ISPD 2016 设计进行评测：

`
python verification/evaluator.py scripts/init.py --benchmark FPGA01
python verification/evaluator.py scripts/init.py --benchmark FPGA07
python verification/evaluator.py scripts/init.py --benchmark FPGA12
`

可用设计：FPGA01 至 FPGA12。

输出为 JSON 对象，包含 combined_score、hpwl、alid 及各合法性门的检查结果。

### 4. 使用 frontier_eval（统一接口）运行

`
python -m frontier_eval task=unified task.benchmark=FPGA/FPGAPlacementOptimization algorithm.iterations=0
`

## Benchmark 数据集

| 数据集 | 位置 | 设计数 | 大小 | 用途 |
|---------|----------|---------|------|------|
| fpga-example1（默认） | references/ | 1 个设计 | ~1 MB | 进化过程中快速迭代 |
| ISPD 2016 | references/ispd2016/（单独下载） | 12 个设计（FPGA01-FPGA12） | ~1 GB | 扩展评测 |

## 参考文献（References）

- **ISPD 2016 FPGA Placement Contest** -- [竞赛页面](http://www.ispd.cc/contests/16/FAQ.html)
- **aug-elfPlace** -- Rachel Selina Rajarathnam 等人, "Better Together: Combining Analytical and Annealing Methods for FPGA Placement," FPL 2024. [GitHub](https://github.com/rachelselinar/DREAMPlaceFPGA)（参考实现）

## 设计文档（Design Documents）

- ClockAwarePlacement_Design_Report.md -- 初始 benchmark 架构设计文档。
- ClockAwarePlacement_DesignValidation.md -- 设计假设的源代码验证；说明为何 "clock-aware" 约束在基线中不存在，以及 benchmark 为何重新表述为纯布局优化问题。
