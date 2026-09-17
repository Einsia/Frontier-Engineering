# CacheReplacement 任务说明

## 1. 背景

### 1.1 工程问题

CPU 缓存容量有限。当新数据载入缓存时，必须选择驱逐哪条旧数据。这个决策——**替换策略（Replacement Policy）**——直接影响缓存命中率和性能。

- LLC 命中率提升 1% → 5–15% 应用加速
- 错误驱逐会导致缓存污染和性能严重下降
- Intel、AMD、ARM、Apple 研究数十年，至今无统一最优解

### 1.2 为什么 LRU 是基线

LRU 是经典替换策略，几乎所有学术研究以 LRU 为默认基线。

**返回 LRU 不代表优化成功。** Score = 1.0 = 等价；score > 1.0 = 超越了数十年启发式算法。

### 1.3 优化搜索空间

| 维度 | 设计内容 |
|---|---|
| metadata 结构 | 跟踪哪些状态（计数器、签名、重用距离） |
| 最近/频率 | 平衡时间局部性和频率 |
| 驱逐选择 | `find_victim()` 决策逻辑 |
| 自适应性 | 检测 workload 阶段切换 |
| 状态压缩 | 64 KB 预算内压缩 |

---

## 2. 任务定义

修改 `replacement/my_policy.cc`（EVOLVE-BLOCK 内）实现替换策略。评估器 4 层验证：

| 层 | 检查 | 失败结果 |
|---|---|---|
| L1: 源码验证 | 禁止头文件/API、动态内存、预算、标记完整性 | `valid=0, score=0` |
| L2: 编译 | ChampSim 增量编译，超时 300s | `valid=0, score=0` |
| L3: 快速验证 | verify_trace 运行不崩溃 | `valid=0, score=0` |
| L4: 正式评测 | 3/10 个 SPEC trace 计算 GMEAN | 失败 trace 跳过 |

### 2.1 输入/输出

- 输入：`replacement/my_policy.h`（成员变量）、`replacement/my_policy.cc`（方法体）
- 输出：`metrics.json`（valid, score, per_trace）

---

## 3. EVOLVE-BLOCK 契约

### 3.1 `.h` 文件 — 成员变量

```cpp
// EVOLVE-BLOCK-START
// 可添加固定大小数组，总 ≤ 64 KB
uint8_t history_table[1024];
// EVOLVE-BLOCK-END
```

### 3.2 `.cc` 文件 — 方法体

可修改三个方法体，不可修改函数签名：

- `find_victim()` — 返回 [0, NUM_WAY)
- `replacement_cache_fill()` — 缓存填充
- `update_replacement_state()` — 状态更新

### 3.3 可用成员

`NUM_WAY`（long）、`last_used_cycles`（vector）、`cycle`（uint64_t）

### 3.4 禁止项

| 类别 | 禁止项 |
|---|---|
| 头文件 | `<iostream>`, `<fstream>`, `<thread>`, `<mutex>`, `<filesystem>`, `<unistd.h>` |
| 文件 I/O | `fopen`, `fread`, `fwrite`, `open(`, `read(`, `mmap(` |
| 系统调用 | `system(`, `popen`, `fork` |
| 线程 | `pthread_`, `std::thread`, `std::async` |
| 动态内存 | `new`, `delete`, `malloc(`, `free(` |
| 动态容器 | `std::vector`, `std::map`, `std::unordered_map`, `std::set`, `std::list` |
| 非确定性 | `rand()`, `srand(`, `random_device`, `mt19937`, `time(` |
| 存储溢出 | 数组总大小 > 64 KB |
| 接口违规 | 修改函数签名、EVOLVE-BLOCK 标记、只读区域 |

---

## 4. 评分

### 4.1 公式

```
score = exp( (1/N) * Σ ln(max(IPC_candidate/ IPC_LRU, 0.001)) )
```

### 4.2 解释

| 分数 | 含义 |
|---|---|
| 1.0 | LRU 等价（基线） |
| > 1.0 | 优于 LRU |
| (0, 1.0) | 差于但有效 |
| 0 | 无效 |

---

## 5. 评测模式

| 模式 | Traces | Warmup | Sim | 时间 | 用途 |
|---|---|---|---|---|---|
| Quick | 3 | 10M | 20M | ~15 min | 迭代 |
| Full | 10 | 50M | 100M | ~30-60 min | 评分 |

---

## 6. 使用方法

```bash
# Quick 模式
python verification/evaluator.py replacement/my_policy.cc --mode quick

# Full 模式
python verification/evaluator.py replacement/my_policy.cc --mode full

# 验证测试
python verification/test_validation.py

# Frontier-Eng 集成
python -m frontier_eval task=unified task.benchmark=ComputerSystems/CacheReplacement algorithm.iterations=0
```

---

## 7. 参考资料

- CRC-2: https://crc2.ece.tamu.edu/
- DPC-3: https://dpc3.compas.cs.stonybrook.edu/
- ChampSim: https://github.com/ChampSim/ChampSim
- 学术论文：`references/related_work.md`
