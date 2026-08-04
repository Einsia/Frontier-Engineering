# AssessmentEngineering

This domain contains lightweight, deterministic, and fully offline benchmark tasks inspired by
psychometrics and operational assessment design.

The tasks translate real assessment requirements—measurement precision, content coverage,
administration time, fairness risk, item exposure, and test security—into reproducible engineering
optimization problems with explicit feasibility constraints.

## Task

- `RobustTestAssembly`: assemble a fixed-length test form from a synthetic item bank while matching
  exact domain quotas, respecting time, DIF-risk, exposure, and shared-material constraints, and
  optimizing measurement information across multiple ability levels.
