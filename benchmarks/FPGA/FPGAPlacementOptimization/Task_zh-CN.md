# 任务：FPGA 布局优化（FPGA Placement Optimization）

## 1. 问题描述（Problem）

改进 `scripts/init.py` 中实现的布局算法。该程序读取 FPGA benchmark 电路（ISPD Bookshelf 格式），将每个逻辑实例（LUT、FF、DSP、BRAM）分配到 FPGA 网格上的合法站点。目标是**最小化半周长线长（Half-Perimeter Wirelength, HPWL）**，同时满足所有 FPGA 特定的合法性约束。

本 benchmark 基于 **ISPD 2016 FPGA Placement Contest** 基准测试集和 **FPGA Bookshelf 格式**（`.nodes`、`.nets`、`.pl`、`.scl`、`.lib`）。

任务：**改进 `scripts/init.py` 中的布局算法以产生更低线长的布局。** 该文件包含一个朴素的逐行扫描布局器（row-scan placer），可生成合法但线长较高的布局。改进后的算法应在保持合法性的前提下降低 HPWL。

## 2. Agent 可修改内容（What the Agent May Modify）

本 benchmark 有意**不指定**任何特定的布局算法。agent 拥有在 `scripts/init.py` 中完全重新设计布局策略的自由。

可能的方法包括但不限于：

- **构造式布局（Constructive placement）** — 使用启发式方法贪婪地放置实例（逐行扫描、二次分配或基于分区的方法）。
- **解析布局（Analytical placement）** — 将布局表述为带有可微线长代理和密度惩罚的连续优化问题。
- **模拟退火（Simulated annealing）** — 从初始布局开始，迭代扰动并改进。
- **强化学习（Reinforcement learning）** — 训练策略网络顺序放置实例。
- **整数规划（Integer programming）** — 将合法性和线长表述为精确优化问题。
- **混合方法（Hybrid approaches）** — 结合多种策略（例如，解析全局布局后接合法化）。


scripts/init.py 中的 EVOLVE-BLOCK 仅包含布局算法函数。
benchmark 解析器（.nodes、.pl、.scl）、输出写入器和 CLI 入口点
位于 EVOLVE-BLOCK 之外，是“冻结”的。评测器在运行时验证该边界——
如果候选程序修改了任何冻结代码，它将获得无效分数。

唯一要求：

1. 程序必须接受相同的命令行接口（`--nodes`、`--pl`、`--scl`、`--output`）。
2. 程序必须按第 7 节（提交契约）描述的 Bookshelf 格式输出 `solution.pl`。
3. 布局必须满足第 6 节（约束）描述的全部三个合法性门（G1、G2、G3）。

评测器**仅评判生成的布局质量和合法性**，而非内部实现。将整个布局算法替换为完全不同方法的 agent，与对逐行扫描布局器进行增量修改的 agent 受到同等对待——两者均仅根据输出布局的 HPWL 和合法性进行评分。

## 3. 输入格式（Input Format, ISPD Bookshelf for FPGA）

Benchmark 设计使用针对 FPGA 布局扩展的 **Bookshelf 格式**。每个设计在 `references/` 中包含以下文件：

| 文件 | 扩展名 | 描述 |
|------|--------|------|
| Auxiliary | `.aux` | 根文件，列出所有其他设计文件 |
| Nodes | `.nodes` | 实例列表（可移动和固定），包含其主单元类型 |
| Nets | `.nets` | 网表：每个 net 连接一组实例引脚 |
| Placement | `.pl` | 实例位置（x, y, z/BEL）——输入仅提供固定 IO 位置 |
| SCL | `.scl` | 站点/时钟布局：站点定义、每站点资源及站点地图网格 |
| Library | `.lib` | 单元库：引脚定义、方向（INPUT/OUTPUT）、时钟/控制属性 |
| Weights | `.wts` | 网权重（通常均为 1.0） |
 架构特定的合法性约束参数 |

`.aux` 文件是入口点：

```
design : design.nodes design.nets design.wts design.pl design.scl design.lib
```

### Nodes 文件

每行格式：`<instance_name> <cell_type>`

```
inst_7 FDRE
inst_8 FDRE
...
inst_3340 IBUF
```

固定实例（IO 焊盘、PLL）在输入 `.pl` 文件中列出，不得移动。

### Nets 文件

每个 net：`net <net_name> <degree>` 后接引脚引用，以 `endnet` 结束：

```
net net_1 3
  inst_7 C
  inst_8 C
  inst_3340 O
endnet
```

### SCL 文件

定义 FPGA 网格：站点类型（SLICE、DSP、BRAM、IO）、每站点资源容量及站点地图布局。

### Library 文件

定义每个单元类型：引脚名称、方向、时钟/控制属性。示例：

```
CELL FDRE
  PIN C INPUT CLOCK
  PIN CE INPUT
  PIN D INPUT
  PIN Q OUTPUT
ENDCELL
```

## 4. 设计变量（Design Variables）

对于每个**可移动**实例 `i`：

- **x 坐标** -- FPGA 网格上的水平位置（整数站点列索引）
- **y 坐标** -- FPGA 网格上的垂直位置（整数站点行索引）
- **z / BEL 索引** -- 站点内的基本元素位置（Basic Element Location, BEL）（整数，如 SLICE 站点为 0-15）

固定实例（IO 焊盘、PLL）具有预定的 (x, y, z) 坐标，必须保持在其输入位置。

## 5. 优化目标（Objective）

最小化**半周长线长（Half-Perimeter Wirelength, HPWL）**：

```
HPWL = sum_{net n} (max_{i in n} x_i - min_{i in n} x_i + max_{i in n} y_i - min_{i in n} y_i)
```

HPWL 根据**最终合法布局**计算，以每个实例所在站点的中心作为其位置。

## 6. 约束条件（Constraints, Hard Validation Gates）

布局解必须满足三个合法性门。任何违反都会使布局失效。

### G1：站点类型兼容性（Site-Type Compatibility）

每个实例必须放置在与其单元类型兼容的站点类型上：

| 单元类型 | 兼容站点类型 |
|----------|-------------|
| LUT6, LUT5, LUT4, LUT3, LUT2, LUT1 | SLICE |
| FDRE, FDCE, FDPE, LDCE | SLICE |
| CARRY4, CARRY8 | SLICE |
| DSP48E2, DSP48E1 | DSP |
| RAMB36E2, RAMB18E2, RAMB36E1, RAMB18E1 | BRAM |
| IBUF, OBUF, BUFGCE, BUFG | IO |

### G2：资源容量（Resource Capacity）

每个站点对每种资源类型有最大容量。对于 SLICE 站点（简化的 Ultrascale 架构）：

- **LUT 容量**：每个 SLICE 16 个（每个 half-SLICE 8 个）
- **FF 容量**：每个 SLICE 16 个（每个 half-SLICE 8 个）
- **DSP 容量**：每个 DSP 站点 1 个
- **BRAM 容量**：每个 BRAM 站点 1 个

布局不得超过这些每站点资源限制。

### G3：进位链完整性（Carry-Chain Integrity）

进位链实例（CARRY4/CARRY8）必须：

- 按正确顺序放置在相邻站点上
- 保持垂直相邻（进位传播方向）

## 7. 提交契约（Submission Contract）

候选程序（`scripts/init.py`）必须：

1. 读取 benchmark 输入文件（`.nodes`、`.nets`、`.pl`、`.scl`、`.lib`）
2. 为所有可移动实例计算布局
3. 将 `.pl` 文件写入指定输出路径

### 输出文件：solution.pl

```
<instance_name> <x> <y> <z>
...
```

示例：

```
inst_7 10 15 8
inst_8 10 15 9
...
inst_3 5  3  0
```

格式规则：
- 字段以空格分隔
- x 和 y 为整数站点列/行坐标
- z 为站点内的整数 BEL 索引
- 固定实例必须保持其在输入 .pl 文件中的原始 (x, y, z) 坐标
- `.nodes` 中的每个可移动实例必须恰好出现一次

## 8. 可行性规则（Feasibility Rules）

满足以下任一条件时，提交无效（不可行）：

1. solution.pl 缺失或无法读取
2. `.nodes` 中的可移动实例未全部出现在 solution.pl 中
3. 任何固定实例被移离其输入位置
4. **G1 违反**：实例放置在不相容的站点类型上
5. **G2 违反**：站点超过其资源容量
6. **G3 违反**：进位链实例违反排序/相邻规则
7. 任何位置字段 (x, y, z) 为非整数、负数或超出器件网格边界
8. solution.pl 包含 `.nodes` 声明之外未定义的额外实例

## 9. 评测流程（Evaluation Workflow）

评测器（`verification/evaluator.py`）：

1. 运行 `python scripts/init.py` 生成 `solution.pl`
2. 解析输入 benchmark 文件（.nodes、.nets、.pl、.scl）
3. 验证 solution.pl 的完整性和格式
4. 检查全部三个合法性门（G1、G2、G3）
5. 使用独立的 NumPy 实现计算 HPWL
6. 返回指标和组合分数

从仓库根目录运行：

```bash
python benchmarks/FPGA/FPGAPlacementOptimization/verification/evaluator.py benchmarks/FPGA/FPGAPlacementOptimization/scripts/init.py
```

或从 benchmark 目录运行：

```bash
cd benchmarks/FPGA/FPGAPlacementOptimization
python verification/evaluator.py scripts/init.py
```

## 10. 评分（Scoring）

- **合法布局（所有门通过）**：combined_score = -HPWL

  HPWL 是所有 net 的原始半周长线长之和。HPWL 越低越好；combined_score 取负值确保数值越大越好。

- **非法布局（任意门未通过或违反可行性规则）**：combined_score = -1e18，valid = 0

## 11. 参考文献（References）

- **ISPD 2016 FPGA Placement Contest**：http://www.ispd.cc/contests/16/FAQ.html
- **aug-elfPlace**：Rachel Selina Rajarathnam 等人, "Better Together: Combining Analytical and Annealing Methods for FPGA Placement," FPL 2024. [GitHub](https://github.com/rachelselinar/DREAMPlaceFPGA)（参考实现，位于仓库根目录 `aug-elfPlace` (separate repository)）

- **ISPD 2016 Benchmark 格式**：`references/README` 描述了 FPGA Bookshelf 格式的扩展内容。
- **Benchmark 数据**：references/（fpga-example1）

## 12. 快速开始（Quick Start）

```bash
# 从 benchmark 目录：
cd benchmarks/FPGA/FPGAPlacementOptimization

# 运行初始求解器：
python scripts/init.py

# 评测结果：
python verification/evaluator.py scripts/init.py

# 预期输出：HPWL ~210721，所有合法性门通过
```
