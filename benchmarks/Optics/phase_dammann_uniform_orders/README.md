# Phase DOE P3: Dammann Uniform Orders

## Background
Optimize binary transition positions for order uniformity and efficiency.

## Structure

```text
task03_dammann_uniform_orders/
  baseline/
    init.py           # candidate: reads problem.npz/json, writes submission.json
  verification/       # scorer-owned, read-only during evaluation
    problem.py        # canonical problem definition (config, aperture/target/spots)
    metrics.py        # canonical forward model + metrics + score
    validate.py       # runs the candidate in isolation, recomputes every number
    outputs/
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## Environment Dependencies
- Use the shared environment file: `benchmarks/Optics/requirements.txt`
- Task03 runtime deps:
  - baseline: `numpy` + local `diffractio` source code in this repository
  - verification/oracle: `scipy`, `matplotlib`
  - local `diffractio` scalar modules additionally need `pandas`, `psutil`
- From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r benchmarks/Optics/requirements.txt
```

## Run

```bash
PYTHONPATH=. python benchmarks/Optics/phase_dammann_uniform_orders/verification/validate.py
```

Oracle = best-of(`SciPy-DE`, literature transition table).

The shared scoring helpers live in `benchmarks/Optics/_shared/phase_common.py`,
outside every benchmark directory so no `copy_files.txt` entry can pull them into
the sandbox the candidate is dropped into.

`baseline/init.py` is not importable as a solver API any more: `validate.py` runs it
as a subprocess in a throwaway directory and reads only `submission.json`. Running it
by hand therefore needs a directory containing `problem.json` / `problem.npz`; the
simplest way to exercise it is to run the validator.
