# RobustTestAssembly

This is a fully offline and deterministic benchmark for psychometric test assembly.

The candidate selects a fixed number of items from a synthetic item bank while satisfying domain quotas, time limits, DIF-risk limits, exposure limits, and shared-material constraints. It should also improve measurement information across multiple ability levels.

## Benchmark ID

`AssessmentEngineering/RobustTestAssembly`

## Local evaluation

Run from the task directory:

`python verification/evaluator.py scripts/init.py`

The initial program should score 50 and remain feasible in all 10 scenarios.

Run the complete test suite with:

`python verification/test_task_v1.py`

## Runtime requirements

- Linux
- Python 3.10 or newer
- Python standard library only
- No GPU, network access, external data, or API key required

All item banks and risk indicators are synthetic. This benchmark evaluates optimization and constraint handling; it does not validate the fairness, validity, or clinical use of a real assessment.
