# Frontier-Eng

English | [简体中文](README_zh-CN.md)

[![Homepage](https://img.shields.io/badge/Homepage-lab.einsia.ai-0969DA?style=flat-square&logo=homepage&logoColor=white)](https://lab.einsia.ai/frontier-eng/)
[![arXiv](https://img.shields.io/badge/arXiv-2604.12290-b31b1b?style=flat-square&logo=arxiv&logoColor=white)](http://arxiv.org/abs/2604.12290)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/kBU7yjBds)

Frontier-Eng is a benchmark for **generative optimization**: agents iteratively edit runnable engineering code, get feedback from frozen verifiers, and improve under a fixed interaction budget. The paper's central claim is simple: engineering performance is usually about the **best design you can discover within budget**, not average pass rate. Frontier-Eng therefore focuses on:

- continuous reward signals instead of binary grading
- real verifiers and simulators instead of judge models
- improvement trajectories instead of single-shot answers

The benchmark currently covers **47 tasks** across computing, quantum information, operations research, robotics and control, optics and communications, and physical sciences. The project homepage and paper frame it as a missing evaluation axis between pass/fail coding benchmarks and real engineering work: most engineering problems start from a feasible baseline and reward iterative improvement, not one-shot correctness.

## News

- **2026-06-30** — **New scoring metric: the Medal Score (gold/silver/bronze).** Alongside average rank, we now release a peer-relative *Medal Score* (normalized to `[0,1]`). On each task the top-3 best-feasible scores in the v1 snapshot are frozen as gold/silver/bronze baselines; a model earns 1.00 / 0.67 / 0.33 for reaching each, averaged over the task set, and is reported on both v1 (47 tasks) and v1-lite (10 tasks). It rewards only reaching each task's frontier and ignores negligible long-tail margins, making cross-task aggregation fairer. Per-task podium values and the leaderboard live in [`leaderboard/`](leaderboard/README.md).
- **2026-06-30** — **`v1-lite` released.** A 10-task representative subset of `v1` covering all five categories with distinct benchmark families, selected for tasks whose scores climb gradually under budget (not one-shot-saturated or all-or-nothing). Run it with `frontier_eval/conf/batch/v1_lite.yaml`.
- **2026-07-17** — **Version branches clarified.** The historical baseline has been frozen at `v1-arxiv` for reproducibility and arXiv-era compatibility. Active development for the next version is now tracked on `main`, and community contributions are welcome there.

## 0. Host Requirements

The repository-owned Python environments are automated, but a full `v1` baseline sweep still assumes a Linux host with the following capabilities already in place:

| Requirement | Needed for | Notes |
|---|---|---|
| Standard build tools and outbound network access | all setup paths | required for `uv`, Python wheels, and benchmark-local downloads |
| NVIDIA GPU + working CUDA stack | `KernelEngineering/*`, `Aerodynamics/CarAerodynamicsSensing`, selected robotics tasks | not needed for CPU-only tasks |
| Docker | `EngDesign` | needed only for that task family |
| Octave | `Astrodynamics/MannedLunarLanding` | host-level tool, not installed by `uv` |
| Extra datasets / checkpoints / third-party repos | selected tasks such as `SustainableDataCenterControl`, `CarAerodynamicsSensing`, `MolecularMechanics` | see task README files for exact paths |

If you want the task-by-task preparation details, including host-tool installation notes, read [`run.md`](run.md) before launching the full `v1` problem set.

## Quickstart

### 1. Install `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

### 2. Create the driver environment

From the repository root:

```bash
bash init.sh
source .venvs/frontier-eval-driver/bin/activate
```

This creates the **driver** environment used to run `python -m frontier_eval`.

### 3. Run a smoke test

```bash
python -m frontier_eval task=smoke algorithm=openevolve algorithm.iterations=0
```

This does not need an API key and is the fastest way to confirm the framework itself is wired correctly.

## Running Real Benchmarks

There are two layers of environments in this repository:

- `frontier-eval-driver`: the driver environment
- `.venvs/<runtime-name>`: task runtime environments such as `frontier-v1-main`, `frontier-v1-kernel`, and `frontier-v1-summit`

To create the v1 task runtime environments used by the released `v1` problem set:

```bash
bash scripts/env/setup_v1_task_envs.sh
```

The runtime selector now uses:

- `task.runtime.env_name=<name>` to prepend `.venvs/<name>/bin` to `PATH`
- `task.runtime.python_path=uv-env:<name>` when a task must call a runtime interpreter directly

### Single-task baseline run

No LLM key is needed for baseline-only validation:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=WirelessChannelSimulation/HighReliableSimulation \
  algorithm=openevolve \
  algorithm.iterations=0
```

### Full `v1` baseline sweep

To validate the released `v1` problem set without any model API calls:

```bash
bash scripts/batch/validate_v1_task_envs.sh
```

That command runs the batch config for the `v1` problem set with `algorithm.iterations=0`, which evaluates each task's shipped baseline instead of asking an LLM to improve it.

### `v1-lite` quick subset

For fast iteration and ablations, use the 10-task `v1-lite` matrix
([`frontier_eval/conf/batch/v1_lite.yaml`](frontier_eval/conf/batch/v1_lite.yaml))
instead of the full `v1` config. It spans all five categories with distinct
benchmark families and favors tasks whose scores improve gradually under budget,
so a short run still exercises the full optimization loop.

If you want the full `v1` problem set with normal optimization runs later, see [`run.md`](run.md).

## Where To Go Next

- Framework commands and task onboarding: [`frontier_eval/README.md`](frontier_eval/README.md)
- Batch-running the released `v1` problem set: [`run.md`](run.md)
- Full task list: [`TASK_DETAILS.md`](TASK_DETAILS.md)
- Archived best solutions from published runs: [`baseline_archive/README.md`](baseline_archive/README.md)

## Leaderboard

Detailed leaderboard (incl. average rank): [lab.einsia.ai/frontier-eng/leaderboard](https://lab.einsia.ai/frontier-eng/leaderboard). Released score tables and the per-task medal podium: [`leaderboard/`](leaderboard/README.md).

**Medal Score** (gold/silver/bronze podium, higher is better, normalized to `[0,1]` = mean per-task podium credit). On each task the top-3 best scores in the **v1 snapshot (2026-04-14)** are frozen as gold/silver/bronze baselines; a model earns 1.00 / 0.67 / 0.33 for reaching each. Reported on both the full **v1** set (47 tasks) and the **v1-lite** subset (10 tasks); gold/silver/bronze counts are for v1 (see [`leaderboard/`](leaderboard/README.md)):

| Rank | Model | Medal (v1) | Medal (v1-lite) | 🥇 | 🥈 | 🥉 |
| :--: | :--- | --: | --: | --: | --: | --: |
| 1 | GPT-5.4 | 0.596 | 0.667 | 24 | 5 | 2 |
| 2 | Claude Opus 4.6 | 0.490 | 0.501 | 9 | 18 | 6 |
| 3 | GLM-5 | 0.312 | 0.233 | 4 | 10 | 12 |
| 4 | DeepSeek V3.2 | 0.248 | 0.166 | 3 | 9 | 8 |
| 5 | Gemini 3.1 Pro Preview | 0.213 | 0.200 | 3 | 6 | 9 |
| 6 | Seed 2.0 Pro | 0.185 | 0.100 | 3 | 7 | 3 |
| 7 | Grok 4.20 | 0.184 | 0.133 | 3 | 6 | 5 |
| 8 | Qwen3 Coder Next | 0.121 | 0.000 | 3 | 3 | 2 |

## Contributing

Contribution guidelines live in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Citation

```bibtex
@article{chi2026frontier,
  title={Frontier-Eng: Benchmarking Self-Evolving Agents on Real-World Engineering Tasks with Generative Optimization},
  author={Chi, Yizhe and Hong, Deyao and Jiang, Dapeng and Luo, Tianwei and Yang, Kaisen and Zhang, Boshi and Cao, Zhe and Fan, Xiaoyan and He, Bingxiang and Hao, Han and others},
  journal={arXiv preprint arXiv:2604.12290},
  year={2026}
}
```
