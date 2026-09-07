# EngDesign 提交格式

`submission/engdesign_submission.py` 必须定义：

```python
SUBMISSION = {
"AM_02": { ... },
"AM_03": { ... },
"CY_03": { ... },
"WJ_01": { ... },
"XY_05": { ... },
"YJ_02": { ... },
"YJ_03": { ... },
}
```

每个任务的值都应与该任务的 `output_structure.py` 兼容。

每个任务的推荐有效载荷结构：

```python

{
    "reasoning": "...",
    "config": {
    }
}
```

注意：

- `CY_03.config.vioblk_read` 和 `CY_03.config.vioblk_write` 是 Python 源代码字符串。
- `CY_03` 提交不能调用基准测试内部的辅助函数 `gold_vioblk_read` / `gold_vioblk_write`。
- `WJ_01.config.function_code` 是 Python 源代码，必须定义 `denoise_image(noisy_img)`。
- 数值型任务得分范围应为 `[0, 100]`；最终的 `combined_score` 是它们的平均值。

## 提交文件只被解析，不被执行

`submission/engdesign_submission.py` 使用 `ast.parse` + 纯字面量求值器读取。
文件中的任何代码都不会执行 —— 无论在编排进程还是各子题子进程中。

可读结构：

- 字面量（`str`、`bytes`、`int`、`float`、`bool`、`None`）
- 由字面量构成的 `list` / `tuple` / `set` / `dict`
- 数字上的一元 `+` / `-`
- 引用本文件中**更早**定义的、绑定到字面量的模块级名字

不可读（提交判为无效，`valid=0`、`combined_score=0`）：函数定义、函数调用
（含 `"...".strip()`）、f-string、推导式、import、属性访问。请直接内联取值。

`CY_03.config.vioblk_read` / `vioblk_write` 与 `WJ_01.config.function_code`
本来就是源码**字符串**：由对应子题的 `evaluate.py` 在自己的隔离子进程中执行。
提交文件本身无需可执行。

若任务日后改为 `.json` 候选文件（顶层对象含 7 个子题键），评测器同样支持。
