# Holographic H4: Polarization-Multiplexed Optical Design

## Background

One optical device can encode different functions for different polarization states.
This task models polarization multiplexing: x-polarized and y-polarized inputs should produce different target patterns.

Application examples:

- polarization-division multiplexing,
- optical security,
- multifunctional meta-optics.

## What the agent should modify

- Target file: `baseline/init.py` -- and only that file.
- It is run as its own process with `problem.json` as its only input and
  `submission.npz` as its only output. See `Task.md` for the full contract.
- Everything under `verification/` is read-only. In particular
  `verification/problem_spec.py` owns the problem definition (grid, wavelengths,
  target coordinates, power ratios, ROI radius and all scoring constants), and
  `verification/evaluate.py` owns the forward physics and the metrics.

## File structure

```text
task4_polarization_multiplexing/
  baseline/
    init.py
  verification/
    evaluate.py
    problem_spec.py
    reference_solver.py
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## Environment dependencies

Recommended interpreter:

```bash
python
```

Shared task requirements file:

- `benchmarks/Optics/requirements.txt`

Install example (from repository root):

```bash
PY=python3
$PY -m pip install -r benchmarks/Optics/requirements.txt
$PY -m pip install -e .
```

If you only run baseline logic and skip oracle, you may remove `slmsuite`/`scipy` from that requirements file.

## How to run

```bash
PY=python3
$PY benchmarks/Optics/holographic_polarization_multiplexing/verification/evaluate.py
```

Artifacts are generated in `verification/artifacts/`.

## Oracle dependency

`verification/reference_solver.py` uses `slmsuite` as a third-party oracle backend.
