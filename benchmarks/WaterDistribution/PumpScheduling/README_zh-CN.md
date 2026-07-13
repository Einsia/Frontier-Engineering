# 配水系统泵站调度

基于 WNTR/EPANET Net3 的纯 CPU、闭环泵站调度基准。统一任务 ID 为
`WaterDistribution/PumpScheduling`。安装依赖后直接评测：

```bash
python -m pip install -r verification/requirements.txt
python verification/evaluator.py scripts/init.py --json-out metrics.json --artifacts-out artifacts.json
```

从仓库根目录运行统一基线评测：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=WaterDistribution/PumpScheduling \
  task.runtime.python_path=/path/to/wntr-python \
  algorithm=openevolve \
  algorithm.iterations=0
```

任务仅需 CPU、WNTR 1.4.0 和 EPANET 运行时，不需要 GPU、Docker、外部数据集
或网络。候选控制器在隔离子进程中仅通过 JSON 因果观测接口执行；评测器本身
仍应只从可信的 benchmark checkout 运行。
