# 安全约束电力调度

本任务要求 Agent 改进发电机有功功率和电压设定值，在由 PGLib-OPF
构建的正常及 N-1 故障场景中降低发电成本。冻结验证器使用独立交流潮流
检查每个候选方案。

## Benchmark ID

```text
PowerSystems/SecurityConstrainedDispatch
```

## 数据来源

任务内置的 MATPOWER 案例来自 PGLib-OPF `v23.07`，提交：
`dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3`。

- `pglib_opf_case24_ieee_rts.m`
- `pglib_opf_case57_ieee.m`
- `pglib_opf_case73_ieee_rts.m`

许可证和文件哈希见 `references/pglib/LICENSE` 与
`references/PROVENANCE.md`。

## 环境

推荐 Linux 与 Python 3.12。本任务仅使用 CPU：

```bash
python -m venv .venv-pglib-scd
source .venv-pglib-scd/bin/activate
python -m pip install -r benchmarks/PowerSystems/SecurityConstrainedDispatch/verification/requirements.txt
```

评测器仅使用 CPU，并要求 Linux seccomp 支持。候选程序在受限 worker
进程中运行，不使用 Docker 或 Linux namespace。worker 会禁止 `solve()`
读取或写入文件、创建进程和访问网络；如果 seccomp 过滤器无法安装，评测将
直接失败，不会降级为无保护执行。由于运行环境不提供 namespace 隔离，本方案
不宣称具备与容器完全等价的安全边界。

候选模块加载使用独立的 10 秒基础设施超时；每次 `solve()` 仍拥有任务合同
规定的完整 2 秒预算，模块加载时间不会占用该预算。

完整12个场景的 baseline 评测通常只需数秒，内存低于2 GB。

## 直接评测

在任务目录执行：

```bash
python verification/evaluator.py scripts/init.py \
  --metrics-out metrics.json \
  --artifacts-out artifacts.json
```

## Frontier Eval

在仓库根目录执行，并传入任务环境的 Python：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=PowerSystems/SecurityConstrainedDispatch \
  task.runtime.python_path=/absolute/path/to/.venv-pglib-scd/bin/python \
  algorithm=openevolve \
  algorithm.iterations=0
```

若环境位于 `.venvs/frontier-pglib-scd`，可以改用：

```text
task.runtime.python_path=uv-env:frontier-pglib-scd
```

完整任务契约和评分方法见 `Task_zh-CN.md`。
