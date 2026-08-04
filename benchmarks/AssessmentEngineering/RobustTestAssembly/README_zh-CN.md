# RobustTestAssembly（稳健心理测验组卷）

这是一个完全离线、可重复运行的心理测量组卷 benchmark。

候选程序需要从合成题库中选择固定数量的题目，同时满足领域配额、作答时间、DIF 风险、题目曝光和材料冲突等限制，并尽可能提高不同能力水平上的测量信息。

## Benchmark ID

`AssessmentEngineering/RobustTestAssembly`

## 本地评测

在任务目录运行：

`python verification/evaluator.py scripts/init.py`

初始程序应得到 50 分，并在 10 个场景中全部合法。

完整自检命令：

`python verification/test_task_v1.py`

## 运行环境

- Linux
- Python 3.10 及以上
- 只使用 Python 标准库
- 不需要 GPU、网络、外部数据或 API Key

所有题库和风险指标均为合成数据。本任务评测组卷优化和约束处理能力，不代表真实测验已经具有效度、公平性或临床价值。
