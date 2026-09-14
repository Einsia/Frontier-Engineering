# Frontier Eval Framework

`Frontier-Engineering` 的评测框架。

## 结构

- `frontier_eval/cli.py`：主入口（`python -m frontier_eval`）
- `frontier_eval/tasks/`：任务实现
- `frontier_eval/algorithms/`：算法实现（`openevolve`、`abmcts`、`shinkaevolve`）
- `frontier_eval/conf/`：Hydra 配置

## 环境准备

推荐走 `uv` 路线。

在仓库根目录执行：

```bash
bash init.sh
source .venvs/frontier-eval-driver/bin/activate
```

这会准备好运行 `python -m frontier_eval` 的 driver 环境。

如果你还想把发布版 `v1` 所需的合并 runtime 一次性建好：

```bash
bash scripts/env/setup_v1_task_envs.sh
```

注意：这一步只准备框架和仓库内维护的 runtime。很多 benchmark 仍然需要 benchmark-local 依赖、外部数据、Docker 或 `third_party/` 仓库。

候选子进程隔离需要 Linux 用户命名空间和 `bubblewrap`（`bwrap`；Debian/Ubuntu 可运行 `sudo apt-get install bubblewrap` 安装）。受限候选只能访问声明的输入且无法联网；隔离不可用时评测报错，不会降级为无隔离运行。

运行具体 benchmark 前，请始终先看：

1. `benchmarks/<Domain>/README*.md`
2. 若该 task 还有自己的 README，再继续看 `benchmarks/<Domain>/<Task>/README*.md`

## runtime 选择方式

`unified` 支持两种常用 runtime 选择方式：

- `task.runtime.env_name=<name>`：把 `.venvs/<name>/bin` 放到 `PATH` 前面
- `task.runtime.python_path=uv-env:<name>`：直接解析为 `.venvs/<name>/bin/python`

也可以显式传绝对路径：

```bash
task.runtime.python_path=/绝对路径/python
```

默认兜底 runtime 是 `frontier-eval-driver`，但很多任务应该使用自己的专用 runtime。

## 快速自检

这几个命令很快，而且不需要额外 benchmark 资源：

```bash
python -m frontier_eval task=smoke algorithm=openevolve algorithm.iterations=0
python -m frontier_eval task=smoke algorithm=shinkaevolve algorithm.max_generations=0
python -m frontier_eval task=smoke algorithm=abmcts algorithm.iterations=0
```

## 运行 unified benchmark

示例：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/MallocLab \
  algorithm=openevolve \
  algorithm.iterations=10
```

如果只是验证 baseline，不调用 LLM：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ComputerSystems/MallocLab \
  algorithm=openevolve \
  algorithm.iterations=0
```

如果任务需要独立 runtime：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=ReactionOptimisation/snar_multiobjective \
  task.runtime.python_path=uv-env:frontier-v1-summit \
  algorithm=openevolve \
  algorithm.iterations=0
```

`EngDesign` 仍然走 unified 流程，但具体使用 Docker 还是本地执行，由任务自己的 wrapper 决定。

## unified 元数据

在 `benchmarks/<Domain>/<Task>/frontier_eval/` 下：

```text
initial_program.txt       # 必需
candidate_destination.txt # 可选
eval_command.txt          # 必需
eval_cwd.txt              # 可选
agent_files.txt           # 可选
copy_files.txt            # 可选
readonly_files.txt        # 可选
artifact_files.txt        # 可选
constraints.txt           # 可选
```

`eval_command.txt` 里常用占位符：

- `{python}`
- `{candidate}`
- `{benchmark}`
- `{sandbox}`
- `{repo_root}`
- `{benchmark_source}`
- `{benchmark_id}`

评测器默认读取：

- `metrics.json`
- 可选 `artifacts.json`

如果缺失 `valid` 或 `combined_score`，unified evaluator 会做合理兜底。

## batch 运行

通用形式：

```bash
python -m frontier_eval.batch --matrix frontier_eval/conf/batch/example_matrix.yaml
```

发布版 `v1`：

```bash
python -m frontier_eval.batch --matrix frontier_eval/conf/batch/v1.yaml
```

主机侧操作方式见 [`run_zh-CN.md`](../run_zh-CN.md) 和 [`run.md`](../run.md)。

batch matrix 里的每个 task 可以携带自己的 runtime override，例如：

```yaml
tasks:
  - name: unified
    label: ReactionOptimisation/dtlz2_pareto
    overrides:
      - task.benchmark=ReactionOptimisation/dtlz2_pareto
      - task.runtime.python_path=uv-env:frontier-v1-summit
```

## `v1` runtime 布局

当前合并 runtime 包括：

- `frontier-v1-main`
- `frontier-v1-summit`
- `frontier-v1-sustaindc`
- `frontier-v1-kernel`

`openff-dev` 仍然是特殊 runtime，因为截至 2026 年，OpenFF 工具链还不能只靠 `uv` 完整复现。
可以单独执行：

```bash
bash scripts/bootstrap/install_openff_dev.sh
```

常用辅助脚本：

- `bash scripts/env/setup_v1_task_envs.sh`
- `bash scripts/batch/validate_v1_task_envs.sh`
- `python scripts/ops/audit_unified_metadata_readonly.py [--strict]`

## 可选 `third_party/` 仓库

有些算法或 benchmark 仍然依赖本地 checkout：

可以直接用统一的 bootstrap 入口准备：

```bash
python scripts/bootstrap/fetch_task_assets.py --target algorithms
python scripts/bootstrap/fetch_task_assets.py --target shinkaevolve
python scripts/bootstrap/fetch_task_assets.py --target abmcts
```

```bash
mkdir -p third_party
git clone https://github.com/SakanaAI/treequest.git third_party/treequest
git clone https://github.com/thuml/PhySense.git third_party/PhySense
```

如果你要跑 `shinkaevolve` 并修改 provider 信息或做本地调试，建议使用本地 checkout。

## 环境变量

推荐使用 `.env`：

```bash
cp .env.example .env
```

`python -m frontier_eval ...` 会自动向上查找并加载最近的 `.env`。

正常优化运行需要 `OPENAI_API_KEY`；如果只是 baseline-only 且 `algorithm.iterations=0`，则不需要。
