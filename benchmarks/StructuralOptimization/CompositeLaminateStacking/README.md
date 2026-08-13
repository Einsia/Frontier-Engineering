# CompositeLaminateStacking

Optimize balanced, symmetric 48-ply composite laminates across ten simply supported
plate cases derived from an MIT-licensed published benchmark.

## What the agent edits

Only [`scripts/init.py`](scripts/init.py) is editable. Implement:

```python
def design_laminates(cases: list[dict]) -> dict[str, list[int]]:
    ...
```

Return one list of 12 integer base angles in `[0, 90]` for every `case_id`. The evaluator
expands the list into a balanced, symmetric 48-ply stack. See [`Task.md`](Task.md) for the
complete contract and [`references/design_notes.md`](references/design_notes.md) for the
mechanics and source cross-check.

## Requirements

- Python 3.10+
- NumPy
- no GPU, Docker, external data, or proprietary solver

Install task-local requirements if needed:

```bash
python -m pip install -r verification/requirements.txt
```

## Direct evaluation

From this task directory:

```bash
python verification/evaluator.py scripts/init.py
python -m unittest discover -s verification -p "test_*.py" -v
```

## Unified evaluation

From the repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=StructuralOptimization/CompositeLaminateStacking \
  algorithm=openevolve \
  algorithm.iterations=0
```

The baseline is feasible in all ten cases and scores 50. Higher is better.
