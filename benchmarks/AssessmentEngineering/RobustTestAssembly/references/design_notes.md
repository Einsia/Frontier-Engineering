# Design Notes

## Purpose

This benchmark evaluates robust psychometric test assembly under simultaneous measurement, content, time, fairness-risk, exposure, and security constraints.

## Synthetic design

The item banks are synthetic so the task is deterministic, redistributable, fully offline, and free of confidential assessment content.

## Scenario design

Ten fixed scenarios vary domain quotas, ability-profile weights, time limits, DIF-risk limits, and exposure limits. Six are development scenarios and four are validation scenarios.

## Baseline and optimization gap

The frozen baseline scores 50.0 and is feasible in all ten scenarios.

An independent local-search fixture that does not import the formal scoring module scores 72.605462 while remaining feasible in all ten scenarios. This verifies meaningful optimization headroom.

## Reproducibility

- Scenario generation uses fixed seeds.
- Scenario names and seeds are hidden from the candidate.
- The evaluator and baseline are deterministic.
- Evaluation uses only the Python standard library.

## Limitations

The benchmark uses a simplified 2PL information model and synthetic scalar proxies for DIF risk and exposure. It does not model empirical calibration uncertainty, multidimensional IRT, real response data, or institutional test-security procedures.
