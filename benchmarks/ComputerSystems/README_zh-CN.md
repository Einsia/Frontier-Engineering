# 计算机系统

包含以下计算机系统工程优化任务：
- `MallocLab`：动态内存分配。
- `DuckDBWorkloadOptimization`：分析型 SQL 负载调优（索引/物化视图选择 + 查询改写）。
- `AdaptiveCompressedTelemetryExecution`：实测 CPU 遥测数据压缩与压缩态查询协同设计。

`AdaptiveCompressedTelemetryExecution` 是一个执行驱动的 C++ 任务：候选编解码
与查询代码会被编译、逐值校验，并在绑定的单个 CPU 上计时；评测同时报告原始
吞吐量、压缩率以及存储与 CPU 综合经济目标。

贡献提示：请确保被 evolve 的 baseline 源码文件包含 `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END` 标记（C/C++ 中使用 `// ...`）。
