# EngDesign Submission Schema

`submission/engdesign_submission.py` must define:

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

Each task value should be compatible with that task's `output_structure.py`.

Recommended payload shape per task:

```python
{
  "reasoning": "...",
  "config": {
    # task-specific fields
  }
}
```

Notes:
- `CY_03.config.vioblk_read` and `CY_03.config.vioblk_write` are Python source strings.
- `CY_03` submissions cannot call benchmark-internal helpers `gold_vioblk_read` / `gold_vioblk_write`.
- `WJ_01.config.function_code` is Python source code and must define `denoise_image(noisy_img)`.
- Numeric task score ranges are expected to be `[0, 100]`; final `combined_score` is their average.

## The submission file is parsed, never executed

`submission/engdesign_submission.py` is read with `ast.parse` plus a literal-only
evaluator. No code in it runs -- not in the orchestrator process, not in the
per-task child processes.

Readable constructs:

- literals (`str`, `bytes`, `int`, `float`, `bool`, `None`)
- `list` / `tuple` / `set` / `dict` displays built from literals
- unary `+` / `-` on numbers
- references to module-level names bound to literals earlier in the same file

```python
CY03_READ = "def vioblk_read(...): ..."   # OK: module-level string literal

SUBMISSION = {
    "CY_03": {"reasoning": "...", "config": {"vioblk_read": CY03_READ, ...}},
    ...
}
```

Not readable (submission becomes invalid, `valid=0`, `combined_score=0`):

```python
CODE = """...""".strip()          # call
TRAJ = [{"t": t} for t in range(20)]  # comprehension
SUBMISSION = {"AM_02": build()}       # call
```

`CY_03.config.vioblk_read` / `vioblk_write` and `WJ_01.config.function_code` are
plain source *strings*: the owning task's `evaluate.py` executes them inside its
own isolated child process. The submission file itself never needs to be runnable.

A `.json` candidate file (a top-level object with the seven task keys) is also
accepted, in case the task is ever reconfigured to use one.
