# CacheReplacement — CPU 缓存替换策略优化

AI agent 通过修改 C++ 代码设计 CPU 缓存替换策略，编译到 [ChampSim](https://github.com/ChampSim/ChampSim) 模拟器中，在 SPEC CPU 2017 内存访问 trace 上进行评测。目标是超越经典的 LRU 基线。

| 快速链接 | |
|---|---|
| 任务说明 | [Task_zh-CN.md](Task_zh-CN.md) / [Task.md](Task.md) |
| 工程领域 | 计算机体系结构 — 微架构优化 |
| 对比已有 benchmark | MallocLab (OS)、DuckDB (数据库) → **CacheReplacement (体系结构)** |
| 竞赛背景 | [Cache Replacement Championship (CRC-2, ISCA 2017)](https://crc2.ece.tamu.edu/) |

---

## 评测管线

```
  Agent 修改 replacement/my_policy.cc（EVOLVE-BLOCK 标记内）
                          │
                          ▼
  ┌──────────────────────────────────────────────────────┐
  │ Layer 1: 源码验证                                    │
  │  · 最佳努力静态扫描                                  │
  │  · 禁止头文件：<iostream>, <fstream>, <thread>       │
  │  · 禁止API：fopen, mmap, system, fork                │
  │  · 禁止随机：rand(), mt19937, time()                 │
  │  · 禁止动态内存：new, delete, malloc, free            │
  │  · 存储预算 ≤ 64 KB（近似检查）                      │
  │  · EVOLVE-BLOCK 完整性检查                            │
  │  失败 → valid=0, score=0                             │
  └──────────────────────┬───────────────────────────────┘
                         │ 通过
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │ Layer 2: 编译到 ChampSim                             │
  │  · config.sh + make -j4（增量编译）                   │
  │  · 环境：g++-13, C++17, -O3 -fno-exceptions           │
  │  · 超时：300s                                        │
  │  失败 → valid=0, score=0                             │
  └──────────────────────┬───────────────────────────────┘
                         │ 通过
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │ Layer 3: 快速验证                                    │
  │  · 运行 verify_trace（10M warmup + 20M sim）          │
  │  · 检查：不崩溃、IPC合法                              │
  │  · 目的：快速拒绝无效策略，不参与评分                  │
  │  · 超时：120s                                        │
  │  失败 → valid=0, score=0                             │
  └──────────────────────┬───────────────────────────────┘
                         │ 通过
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │ Layer 4: 正式评测                                    │
  │  · Quick 模式：3 traces，~15 min                      │
  │  · Full 模式：10 traces，~30-60 min                   │
  │  · 每个 trace：50M warmup + 100M simulation           │
  │  · 从 ChampSim 输出提取 IPC                          │
  │  · score = GMEAN(IPC_candidate / IPC_LRU)             │
  │  · 失败的 trace 跳过，剩余继续                        │
  └──────────────────────┬───────────────────────────────┘
                         │
                         ▼
              输出：{valid, score, per_trace, error}
```

---

## 评分

```
score = geometric_mean( IPC_candidate[t] / IPC_LRU[t] )

  score = 1.0    → 等价于 LRU 基线
  score > 1.0    → 优于 LRU
  score ∈ (0,1)  → 差于 LRU 但功能有效
  score = 0      → 无效（安全/编译/运行时失败）
```

### metrics.json 输出示例

```json
{
    "valid": true,
    "score": 1.15,
    "benchmark_version": "1.0.0",
    "mode": "full",
    "num_traces_completed": 10
}
```

失败时：

```json
{
    "valid": false,
    "score": 0.0,
    "error": "Static validation: Forbidden header: <iostream>"
}
```

---

## 评测模式

| 模式 | Traces | Warmup | Simulation | 预期时间 | 用途 |
|---|---|---|---|---|---|
| **Quick** (`--mode quick`) | 3 (mcf, x264, cactuBSSN) | 10M | 20M | ~15 min | Agent 迭代 |
| **Full** (`--mode full`) | 全部 10 个 | 50M | 100M | ~30-60 min | 最终评分 |

---

## EVOLVE-BLOCK 契约

Agent 修改 **两个文件**，每个都有 `// EVOLVE-BLOCK-START` / `// EVOLVE-BLOCK-END` 标记：

### `replacement/my_policy.h` — 成员变量

```cpp
// EVOLVE-BLOCK-START
uint8_t history_table[1024];     // 1 KB
uint16_t counters[64];           // 128 bytes
// 总计 ≤ 64 KB
// EVOLVE-BLOCK-END
```

### `replacement/my_policy.cc` — 方法实现

```cpp
// EVOLVE-BLOCK-START
// 可修改：find_victim()、replacement_cache_fill()、update_replacement_state()
// 不可修改：函数签名、EVOLVE-BLOCK 外的代码
// EVOLVE-BLOCK-END
```

### 禁止行为（立即拒绝，valid=0）

| 类别 | 示例 | 检测方式 |
|---|---|---|
| **头文件** | `<iostream>`, `<fstream>`, `<thread>`, `<mutex>`, `<filesystem>` | 头文件扫描 |
| **文件 I/O** | `fopen`, `fread`, `mmap(`, `open(` | API 扫描 |
| **系统调用** | `system(`, `popen`, `fork` | API 扫描 |
| **线程** | `pthread_`, `std::thread`, `std::async` | API 扫描 |
| **动态内存** | `new`, `delete`, `malloc(`, `free(` | 正则扫描 |
| **动态容器** | `std::vector`, `std::map`, `std::unordered_map` | 容器扫描 |
| **非确定性** | `rand()`, `srand(`, `random_device`, `mt19937`, `time()` | 函数扫描 |
| **存储溢出** | 声明的数组总大小 > 64 KB | 静态求和 |
| **接口违规** | 删除 EVOLVE-BLOCK 标记、修改只读区域 | diff 检测 |

---

## 安装与运行

### 前置条件

- Python 3.10+
- 支持 C++17 的编译器（g++-12+ 或 clang）
- CMake ≥ 3.22
- ~10 GB 磁盘空间

### 安装步骤

```bash
# 1. 克隆 ChampSim
git clone https://github.com/ChampSim/ChampSim.git data/ChampSim
cd data/ChampSim && git checkout 51588e1d && git submodule update --init && ./vcpkg/bootstrap-vcpkg.sh && ./vcpkg/vcpkg install && cd ../..

# 2. 下载 traces
bash data/download_traces.sh

# 3. 安装 Python 依赖
pip install -r verification/requirements.txt

# 4. 运行基线测试
python verification/evaluator.py replacement/my_policy.cc --mode quick
```

### 验证测试

```bash
python verification/test_validation.py
```

预期：全部 10 个测试通过。

---

## 与现有 ComputerSystems benchmark 对比

| Benchmark | 工程领域 | Agent 操作 | 语言 |
|---|---|---|---|
| `MallocLab` | 操作系统内存管理 | 实现 malloc/free/realloc | C |
| `DuckDBWorkloadOptimization` | 数据库查询优化 | 选择索引 + 改写 SQL | Python |
| **`CacheReplacement`** | **计算机体系结构** | **设计缓存替换策略** | **C++** |

---

## 参考资料

- Cache Replacement Championship (CRC-2): https://crc2.ece.tamu.edu/
- Data Prefetching Championship (DPC-3): https://dpc3.compas.cs.stonybrook.edu/
- ChampSim: https://github.com/ChampSim/ChampSim
- SPEC CPU 2017 traces: https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu/
