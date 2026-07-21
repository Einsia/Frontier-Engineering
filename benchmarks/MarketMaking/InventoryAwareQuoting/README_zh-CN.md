# 库存感知做市报价

设计一个确定性策略，为三组合成股票的 DUAL 品种持续提供买卖报价。主市场提供公允价值参考，
报价相对 DUAL 最优买卖价的竞争力决定成交。策略需要同时权衡价差收益、不利选择、手续费、
流动性变化和库存风险。

每次观察还包含可组合的自然语言做市台指令。策略需要在流动性支持、毒性流防御和库存回收之间
进行结构化分支；固定的一组报价数值被有意设计为无法通过全部可行性约束。

只能修改 `scripts/init.py` 的 EVOLVE-BLOCK，并保持
`decide_quotes(observation) -> dict` 接口有效。

## 环境准备

本任务完全离线、仅使用 CPU。在任务目录执行：

```bash
python -m pip install -r verification/requirements.txt
```

基线评测不需要数据集、交易所连接、GPU、Docker 或模型 API。普通笔记本上的直接评测通常
可在20秒内完成。

## 直接评测

```bash
python verification/evaluator.py scripts/init.py \
  --metrics-out metrics.json --artifacts-out artifacts.json
```

## 回归测试

```bash
python -m unittest discover -s verification -p "test_*.py" -v
```

## Unified 评测

在仓库根目录使用 benchmark id `MarketMaking/InventoryAwareQuoting`。仓库已包含对应 task config，
因此可以直接发现并运行：

```bash
python -m frontier_eval task=inventory_aware_quoting \
  algorithm=openevolve algorithm.iterations=0
```

在仓库支持的 Linux 环境中不需要任务专用 runtime override。`metrics.json` 保存正式排名分、
连续诊断分和可行性；`artifacts.json` 保存12个开发市场状态的详细反馈，以及8个确定性验证状态
的汇总反馈。

候选策略在有加载、单步决策和总时长限制的独立子进程中运行。这可以阻止候选修改父评分器，
或从父进程读取尚未发生的市场路径；它属于进程隔离，而不是操作系统级安全沙箱。

完整观察/动作接口、模拟器、硬约束和评分方式见 `Task_zh-CN.md`；建模取舍、验证设计和限制见
`references/design_notes.md`。
