# 动态内存分配

实验内容来自 [清华大学计算机系统概论2023年 Malloc Lab](https://github.com/PKUanonym/REKCARC-TSC-UHT/tree/master/%E5%A4%A7%E4%BA%8C%E4%B8%8A/%E8%AE%A1%E7%AE%97%E6%9C%BA%E7%B3%BB%E7%BB%9F%E6%A6%82%E8%AE%BA/hw/2023)
实验相关文件位于 `benchmarks/ComputerSystems/MallocLab/malloclab-handout`
更多详细信息请查看 [Task](Task_zh-CN.md)

提示：被 evolve 的候选文件为 `malloclab-handout/mm.c`。请保持函数签名不变，并保留 `// EVOLVE-BLOCK-START` / `// EVOLVE-BLOCK-END` 标记，便于演化算法安全地应用 diff。

正式评分将分配器编译为 Wasm64，由模块外的可信驱动进行验证和计时。在仓库根目录安装一次 Linux x86-64 工具链：

```bash
python benchmarks/_shared/malloc_wasm/setup.py --install
bash benchmarks/ComputerSystems/MallocLab/frontier_eval/run_eval.sh python3 benchmarks/ComputerSystems/MallocLab
```

分数使用隔离运行时中的调用耗时；原生 `make && ./mdriver -V` 可用于本地调试。运行时保留 64 位指针和 20 MiB 模拟堆，需要 Linux 用户命名空间、bubblewrap 和本机 C 编译器。可用 `FRONTIER_MALLOC_TOOLCHAIN` 指定工具链安装目录。
