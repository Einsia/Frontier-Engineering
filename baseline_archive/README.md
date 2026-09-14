# `baseline_archive`

English | [简体中文](#简体中文)

`baseline_archive/` is a root-level snapshot of the final global best code produced by our agent runs for each available experiment / algorithm / model / task combination. It serves as a reference baseline for the community. The current leaderboard
uses replacement best programs for GPT-5.4 on SingleCell and Quantum task 01,
Claude on Quantum task 01, and Gemini on Quantum task 03. These replacements
come from runs with different iteration budgets; Claude's replacement is the
initial baseline retained as best. Other archived programs are preserved,
including submissions marked invalid in the current leaderboard.

## Layout

```text
baseline_archive/
└── <experiment>/
    └── <algorithm>/
        └── <model>/
            └── <task>/
                └── <code-file>
```

## Usage

- Check `baseline_archive/coverage.json` first to confirm coverage for a specific experiment, algorithm, or model.
- Open the task directory directly to get the final best code file for that combination. Example paths:
  - `baseline_archive/experiment1/openevolve/gpt-5.4/Astrodynamics_MannedLunarLanding/`
  - `baseline_archive/experiment2/shinkaevolve/claude-opus-4.6/KernelEngineering_TriMul/`
- Filenames keep the original source suffix and task-local naming, so you may see `.py`, `.c`, `.cpp`, or other benchmark-specific filenames.

---

## 简体中文

`baseline_archive/` 位于仓库根目录，收录我们 agent 实验在各实验 / 算法 / 模型 / task 组合上产出的最终全局 best 代码，可作为社区参考 baseline。当前榜单已替换 GPT-5.4 的 SingleCell、Quantum task 01，Claude 的 Quantum task 01，以及 Gemini 的 Quantum task 03 所对应的 best 程序。补跑的迭代预算不同；Claude 对应的 best 仍为初始基线。其他归档代码保留，包括当前榜单已判无效的提交。

### 目录结构

与上文 **Layout** 相同。

### 使用说明

- 若要确认某个实验、算法或模型是否已收录，先看 `baseline_archive/coverage.json`。
- 进入对应 task 目录即可获取该组合的最终 best 代码；示例路径见上文 **Usage**。
- 文件名保留任务内原始命名与后缀，因此可能是 `.py`、`.c`、`.cpp` 等。
