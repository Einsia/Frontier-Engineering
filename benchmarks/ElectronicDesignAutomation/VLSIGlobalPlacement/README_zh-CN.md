# VLSI 全局布局

全局布局是 VLSI（超大规模集成电路）物理设计中的关键阶段。
在逻辑综合和布图规划之后，标准单元和宏单元必须放置在芯片上，
以最小化线长，同时满足物理约束。

本基准测试使用 **ISPD 2005** 布局竞赛基准，这是 VLSI 布局领域
行业标准的开源基准套件。Agent 必须实现一个最小化半周长线长（HPWL）
的布局算法，同时不违反硬约束。

## 文件结构

```text
VLSIGlobalPlacement/
├── .gitignore                        # Git 忽略规则
├── datasets/                         # 原始 ISPD 2005 Bookshelf 数据
│   └── ispd2005/                     # （空目录；预处理后的 JSON 在 references/ 中）
├── README.md                         # 导航文档（英文）
├── README_zh-CN.md                   # 导航文档（中文，本文件）
├── Task.md                           # 详细任务描述（英文）
├── Task_zh-CN.md                     # 详细任务描述（中文）
├── references/                       # 基准参考数据
│   ├── adaptec1.json.gz                  # 简单基准（约21万单元，gzip）
│   ├── adaptec1_difficulty.json       # 难度元数据
│   ├── adaptec3.json.gz                  # 中等基准（约45万单元）
│   └── adaptec3_difficulty.json       # 难度元数据
├── scripts/
│   ├── init.py                        # [可修改] 布局算法
│   └── preprocess.py                  # Bookshelf 格式转 JSON
├── verification/
│   ├── evaluator.py                   # 评分和合法性检查
│   ├── requirements.txt               # Python 依赖
│   └── docker/
│       └── Dockerfile                 # 容器化评测
├── baseline/
│   └── solution.py                    # 行式放置基线
└── frontier_eval/                     # Unified task 元数据
    ├── initial_program.txt
    ├── eval_command.txt
    ├── agent_files.txt
    ├── artifact_files.txt
    ├── readonly_files.txt
    ├── copy_files.txt
    ├── candidate_destination.txt
    ├── eval_cwd.txt
    ├── constraints.txt
    └── run_eval.py
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r verification/requirements.txt
```

### 2. 运行基线求解器

```bash
cd benchmarks/ElectronicDesignAutomation/VLSIGlobalPlacement
python scripts/init.py
# 输出: temp/submission.json
```

### 3. 评估候选程序

```bash
cd benchmarks/ElectronicDesignAutomation/VLSIGlobalPlacement
python verification/evaluator.py scripts/init.py --benchmark adaptec1
```

### 4. 使用 Unified Task 框架运行

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ElectronicDesignAutomation/VLSIGlobalPlacement \
  algorithm=openevolve \
  algorithm.iterations=0
```

## 基准数据

| 名称 | 难度 | 固定单元 | 可移动单元 | 网络数 | 引脚数 | 芯片尺寸 |
|------|------|---------|-----------|--------|--------|---------|
| adaptec1 | 简单 | 543 | 210,904 | 221,142 | 944,053 | 11589x11589 |
| adaptec3 | 中等 | 723 | 450,927 | 466,758 | 1,875,039 | 23190x23386 |

## 任务概要

- **输入**：芯片尺寸、单元库、固定/可移动单元、网表、初始布局
- **输出**：每个可移动单元的 (x, y) 坐标
- **硬约束**：不移动固定单元、所有单元在芯片内、无重叠
- **优化目标**：最小化半周长线长（HPWL）
- **可编辑文件**：scripts/init.py（仅 place_components() 函数）

## 数据集许可

ISPD 2005 基准由 ICCAD 2005 / ISPD 2006 布局竞赛委员会创建，
可免费用于学术用途。

## 压缩 JSON 格式

参考文件为 gzip 压缩的 JSON，并采用紧凑的网表表示。
每个网表存储为整数单元索引列表，而非完整的引脚字典：

```json
{"netlist": [[0, 1, 2], [3, 4], ...]}
```

紧凑网表相比详细格式可减少约 65% 的 JSON 大小，
gzip 进一步将磁盘占用减少约 84%（adaptec1：22.6MB -> 3.7MB，adaptec3：48.2MB -> 7.9MB）。
scripts/init.py 和 verification/evaluator.py 中的 _decompress_netlist() 函数
在加载时重建完整的引脚字典。该转换相对于 HPWL 计算是无损的。
scripts/preprocess.py 脚本直接从原始 Bookshelf 数据生成此压缩格式。
