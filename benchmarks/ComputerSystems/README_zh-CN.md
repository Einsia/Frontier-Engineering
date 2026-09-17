# 计算机系统

包含以下计算机系统工程优化任务：
- `MallocLab`：动态内存分配。
- `DuckDBWorkloadOptimization`：分析型 SQL 负载调优（索引/物化视图选择 + 查询改写）。
- `CacheReplacement`：CPU 缓存替换策略优化。（替代已删除的 `IndexOptimization`，因其与 `DuckDBWorkloadOptimization` 功能重叠。）

贡献提示：请确保被 evolve 的 baseline 源码文件包含 `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END` 标记（C/C++ 中使用 `// ...`）。
