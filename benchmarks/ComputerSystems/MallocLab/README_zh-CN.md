# 动态内存分配

实验内容来自 [清华大学计算机系统概论2023年 Malloc Lab](https://github.com/PKUanonym/REKCARC-TSC-UHT/tree/master/%E5%A4%A7%E4%BA%8C%E4%B8%8A/%E8%AE%A1%E7%AE%97%E6%9C%BA%E7%B3%BB%E7%BB%9F%E6%A6%82%E8%AE%BA/hw/2023)
实验相关文件位于 `benchmarks/ComputerSystems/MallocLab/malloclab-handout`
更多详细信息请查看 [Task](Task_zh-CN.md)

提示：被 evolve 的候选文件为 `malloclab-handout/mm.c`。请保持函数签名不变，并保留 `// EVOLVE-BLOCK-START` / `// EVOLVE-BLOCK-END` 标记，便于演化算法安全地应用 diff。

## 分数如何送达评分器

`mm.c` 会被编译进 `mdriver`，所以 `mdriver` 打印的任何东西，你的分配器同样打印得出来。
因此分数不再走 stdout：`mdriver` 把一份 JSON 记录写到 `-o` 指定的路径，并盖上评分器
经 stdin 交给它的**单次运行令牌**——该令牌在第一次调用分配器之前就已被读走并关闭。
评分器只认这份记录。

对分配器的两点约束：

* 自己打印 `Score = ... = N/100` 不起任何作用。
* `mm.c` 不得读取 stdin。若 `main()` 取令牌时它已被消耗，本次运行直接判零。

这堵住的是**通道**，不是**进程边界**：候选代码与评分代码共享同一地址空间，而这是题目本身
的性质决定的——分配器必须运行在被测量分配行为的那个程序里。本题的评分建立在「提交的是
诚实分配器」这一前提上。明知未堵的那条路径见
`frontier_eval/known_exploit_token_replay.c`。
