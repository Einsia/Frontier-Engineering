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

公共评分工具在 `benchmarks/Optics/_shared/phase_common.py`，位于所有 benchmark 目录之外，
任何 `copy_files.txt` 条目都无法把它拷进候选所在的沙箱。

`baseline/init.py` 不再是可被 import 的求解器接口：`validate.py` 会在一次性临时目录里以子进程
运行它，并且只读取 `submission.json`。因此手工单独运行它需要一个含 `problem.json` / `problem.npz`
的目录；最简单的方式是直接跑 validator。
