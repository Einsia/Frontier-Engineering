# CompositeLaminateStacking

在十个简支板工况上优化平衡、对称的 48 层复合材料铺层。任务参数来自一个采用
MIT 许可证发布的真实研究 benchmark。

## Agent 修改内容

仅允许修改 [`scripts/init.py`](scripts/init.py)，并实现：

```python
def design_laminates(cases: list[dict]) -> dict[str, list[int]]:
    ...
```

必须为每个 `case_id` 返回一个包含 12 个 `[0, 90]` 区间整数角度的列表。评测器会
把它展开为平衡、对称的 48 层铺层。完整接口见 [`Task_zh-CN.md`](Task_zh-CN.md)，
力学模型与来源交叉验证见 [`references/design_notes.md`](references/design_notes.md)。

## 环境要求

- Python 3.10+
- NumPy
- 不需要 GPU、Docker、外部数据或商业求解器

如有需要，可安装任务依赖：

```bash
python -m pip install -r verification/requirements.txt
```

## 直接评测

在当前任务目录运行：

```bash
python verification/evaluator.py scripts/init.py
python -m unittest discover -s verification -p "test_*.py" -v
```

## Unified 评测

在仓库根目录运行：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=StructuralOptimization/CompositeLaminateStacking \
  algorithm=openevolve \
  algorithm.iterations=0
```

baseline 在全部十个工况中均可行，得分为 50；分数越高越好。
