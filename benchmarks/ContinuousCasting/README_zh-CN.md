# ContinuousCasting

本 domain 汇集"连铸（连续浇铸钢材）及其相邻工业过程控制"的**确定性工程优化**任务。
当前任务强调真实工况约束、明确的材料利用率目标，以及可执行、纯标准库的验证。

## 任务

- `CuttingOptimization`
  - Unified 基准：`task=unified task.benchmark=ContinuousCasting/CuttingOptimization`
  - 快速运行：`python -m frontier_eval task=unified task.benchmark=ContinuousCasting/CuttingOptimization algorithm.iterations=0`
  - 描述：把一根连续浇铸的钢坯（带固定的 0.8 m 零废段）切成成品段，先最小化报废总长度，
    再让每块成品尽量贴近客户目标值——灵感来自 2021 全国大学生数学建模竞赛 D 题。最优可达
    （强 agent 能推导出精确划分 DP）。
- `CuttingOptimizationOnline`
  - Unified 基准：`task=unified task.benchmark=ContinuousCasting/CuttingOptimizationOnline`
  - 快速运行：`python -m frontier_eval task=unified task.benchmark=ContinuousCasting/CuttingOptimizationOnline algorithm.iterations=0`
  - 描述：**在线（闭环）版**——agent 只在报废段距切割线 `reveal_lead` 米以内时才得知其存在，
    每个决策点只拿可见过去，最后按完整隐藏报废表评分。在线 agent 无法达到全知最优（信息不对称），
    因此比离线版更难。
