# BSM1 曝气控制

为基于 IWA 一号基准仿真模型（BSM1）的活性污泥处理厂设计确定性反馈控制器。控制器设置三个好氧反应池的氧传质系数与内回流量，并在旱天、降雨和暴雨场景下权衡出水质量、能耗、达标情况和执行器平滑性。

只修改 `scripts/init.py` 中的 EVOLVE-BLOCK，并保持以下接口：

```python
def reset_controller(scenario: dict) -> None: ...
def control(observation: dict) -> dict: ...
```

## 环境安装

本任务离线运行且只需要 CPU：

```bash
python -m pip install -r verification/requirements.txt
```

仓库不再分发 IWA 原始进水文件。评测器依据已发表的 BSM1 平均值与天气事件说明生成确定性轨迹。在普通笔记本上完整基准评测约需 45 秒。

## 直接评测

```bash
python verification/evaluator.py scripts/init.py --metrics-out metrics.json --artifacts-out artifacts.json
```

## 回归测试

```bash
python -m unittest discover -s verification -p "test_*.py" -v
```

## 统一评测

在仓库根目录运行：

```bash
python -m frontier_eval task=unified task.benchmark=WastewaterTreatment/BSM1AerationControl algorithm=openevolve algorithm.iterations=0
```

排名指标为 `combined_score`，越高越好。`metrics.json` 给出聚合分数与有效性；`artifacts.json` 给出逐场景工程指标和每日出水样本。候选代码运行在带时限的独立 JSON-lines 工作进程中；这是进程隔离，不是操作系统级安全沙箱。

完整接口和评分模型见 `Task_zh-CN.md`，来源、验证和模型限制见 `references/design_notes.md`。
