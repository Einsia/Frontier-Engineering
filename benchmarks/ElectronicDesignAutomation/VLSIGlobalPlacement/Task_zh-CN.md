# VLSI 全局布局

## 1. 工程背景

VLSI 全局布局是 ASIC 物理设计流程中的关键阶段。
在逻辑综合将 RTL 转换为门级网表、布图规划定义芯片轮廓和宏单元位置之后，
全局布局为所有标准单元分配大致位置。

完整的工业流程为：

```
RTL → 逻辑综合 → 布图规划 → 全局布局 → 详细布局
→ 时钟树综合 → 布线 → 时序签核 → 物理验证
```

全局布局是互连线长变得可见的第一步。它产生一个**粗略但合法**的布局，
详细布局器在此基础上进行优化。全局布局的质量直接影响：

- **布线拥塞**：不良布局会产生布线热点
- **时序**：更长的导线增加 RC 延迟
- **功耗**：更长的导线增加动态功耗
- **面积**：低效布局可能需要更大的芯片面积

现代工业布局器（Cadence Innovus、Synopsys ICC2、OpenROAD）
都包含一个全局布局阶段，在保持密度约束的同时优化 HPWL。

## 2. 问题定义

### 输入

基准测试提供以下 JSON 格式的数据：

| 字段 | 类型 | 描述 |
|------|------|------|
| benchmark_name | string | 基准标识符 |
| die | dict | 芯片尺寸：{width, height, row_height, min_x, min_y} |
| cells | dict | 单元库：{cell_name: {width, height}} |
| fixed_cells | list[str] | 固定（I/O）单元名称 |
| movable_cells | list[str] | 可移动（标准）单元名称 |
| initial_placement | dict | 初始位置：{cell_name: {x, y, orientation}} |
| netlist | list[list[dict]] | 网表：[[{cell, x_offset, y_offset}, ...], ...] |
| num_nets | int | 网络总数 |
| num_pins | int | 引脚总数 |

### 输出

布局算法必须生成一个字典，将每个可移动单元名称映射到其 [x, y] 坐标：

```json
{
  "cell_name_1": [x_coordinate, y_coordinate],
  "cell_name_2": [x_coordinate, y_coordinate],
  ...
}
```

固定单元必须保持在其初始位置。

### 硬约束

评测器强制执行三个硬约束：

1. **固定单元不得移动**：任何与初始位置偏差超过 1e-6 的固定单元
   将使布局无效。

2. **所有单元必须在芯片边界内**：每个单元必须满足
    <= x <= die_width - cell_width 且  <= y <= die_height - cell_height。

3. **单元不得重叠**：对于任意两个单元，重叠面积必须为零。
   评测器检查轴对齐边界框的交集。

违反任何硬约束将设置 valid = 0 和 combined_score = -1e18。

### 优化目标

**最小化半周长线长（HPWL）**。

对于每个网络，HPWL 定义为：

```
HPWL(net) = (max(x_pins) - min(x_pins)) + (max(y_pins) - min(y_pins))
```

总 HPWL = 所有网络的 HPWL 之和。

引脚位置计算如下：

```
pin_x = cell_x + cell_width / 2 + x_offset
pin_y = cell_y + cell_height / 2 + y_offset
```

较低的 HPWL 表示更好的布局。有效布局的 combined_score 为 -HPWL，
因此 combined_score 越高越好。

## 3. 为什么选择 HPWL？

HPWL 是 VLSI 布局中的标准优化目标，因为：

- **确定性**且易于计算
- 与布线线长**强相关**
- 是时序、功耗和拥塞的**代理指标**
- 被**所有主要布局竞赛**（ISPD、ICCAD、DAC）使用
- 被**所有主要开源布局器**（RePlAce、ePlace、NTUPlace3、DREAMPlace、OpenROAD）优化

## 4. 基线算法

提供的基线使用**确定性行式布局**：

- 固定单元保持在其初始位置
- 可移动单元按高度（降序）、面积（降序）、名称排序
- 较高的宏单元（height > row_height）优先放置，跨越多行
- 标准单元（height == row_height）从左到右填充剩余行空间
- 布局是确定性的，始终生成合法布局
- HPWL 故意较差，为智能体提供充分的优化空间

## 5. 数据集

来自 ISPD 2005 布局竞赛套件的两个基准：

| 基准 | 难度 | 可移动单元 | 网络数 | 引脚数 | 芯片尺寸 |
|------|------|-----------|--------|--------|---------|
| adaptec1 | 简单 | 210,904 | 221,142 | 944,053 | 11589x11589 |
| adaptec3 | 中等 | 450,927 | 466,758 | 1,875,039 | 23190x23386 |

原始 Bookshelf 格式数据（datasets/ispd2005/）未重新分发。
预处理后的 JSON 文件位于 references/。预处理脚本
scripts/preprocess.py 展示了 Bookshelf 格式如何转换为 JSON。

## 6. 评测

评测器（verification/evaluator.py）：

1. 在干净的子进程中运行候选程序（带超时）
2. 从候选程序读取 	emp/submission.json
3. 检查硬约束（固定单元、边界、重叠）
4. 计算 HPWL
5. 返回指标：combined_score、valid、hpwl、runtime_s

### 命令

```bash
python verification/evaluator.py scripts/init.py --benchmark adaptec1
```

### 指标

| 指标 | 描述 |
|--------|------|
| hpwl | 总半周长线长 |
| valid | 满足所有硬约束则为 1.0，否则为 0.0 |
| combined_score | 有效时为 -hpwl，无效时为 -1e18 |
| runtime_s | 总评测运行时间（秒） |
| n_cells_placed | 布局输出中的单元数量 |
| n_fixed_moved | 被移动的固定单元数量 |
| n_out_of_bounds | 超出芯片边界的单元数量 |
| n_overlaps | 重叠单元对的数量 |

## 7. 参考文献

- ISPD 2005 Placement Contest: https://www.ispd.cc/contests/05/ispd05.html
- ICCAD 2005 Mixed-Size Placement Contest: https://www.sigda.org/programs/placement-contest/
- DREAMPlace: https://github.com/limbo018/DREAMPlace
- RePlAce: https://github.com/The-OpenROAD-Project/RePlAce
- ePlace: https://github.com/limbo018/ePlace
- OpenROAD: https://github.com/The-OpenROAD-Project/OpenROAD
