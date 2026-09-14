# 相位 DOE P2：高难度 Fourier 图案全息

## 背景
纯相位重建稀疏高对比目标，并包含必须抑制的暗区（keep-out 区域）。

## 目录结构

```text
task02_fourier_pattern_holography/
  baseline/
    init.py           # 候选：读 problem.npz/json，写 submission.json
  verification/       # 评分侧所有，评测期间只读
    problem.py        # 权威题目定义（配置、孔径/目标/焦点）
    metrics.py        # 权威前向模型 + 指标 + 分数
    validate.py       # 隔离运行候选，自己重算全部数字
    outputs/
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## 环境依赖
- 使用统一依赖文件：`benchmarks/Optics/requirements.txt`
- Task02 运行依赖：`numpy`、`matplotlib`、`slmsuite`
- 在仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r benchmarks/Optics/requirements.txt
```

## 运行

```bash
PYTHONPATH=. python benchmarks/Optics/phase_fourier_pattern_holography/verification/validate.py
```

oracle：`slmsuite` 的 `WGS-Kim`。

公共评分工具位于 `benchmarks/Optics/_shared/phase_common.py`。

`validate.py` 在子进程的临时工作目录中运行 `baseline/init.py`，并读取 `submission.json`。
手动运行需要在工作目录中准备 `problem.json` 和 `problem.npz`；运行 validator 会准备这些输入。
