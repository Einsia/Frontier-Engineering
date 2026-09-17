# ContinuousCasting

This domain collects deterministic engineering-optimization tasks for continuous steel casting
(连铸) and the adjacent industrial process-control problems. Current tasks emphasize realistic
operational constraints, a well-defined material-utilization objective, and executable,
standard-library-only verification.

## Tasks

- `CuttingOptimization`
  - Unified benchmark: `task=unified task.benchmark=ContinuousCasting/CuttingOptimization`
  - Quick run: `python -m frontier_eval task=unified task.benchmark=ContinuousCasting/CuttingOptimization algorithm.iterations=0`
  - Description: cut a continuously cast steel billet (with fixed 0.8 m scrap segments) into
    pieces to minimize total scrapped length, then make every shipped piece as close as possible
    to a customer target length — inspired by the CUMCM 2021 Problem D. The optimum is reachable
    (a strong agent can derive the exact partition DP).
- `CuttingOptimizationOnline`
  - Unified benchmark: `task=unified task.benchmark=ContinuousCasting/CuttingOptimizationOnline`
  - Quick run: `python -m frontier_eval task=unified task.benchmark=ContinuousCasting/CuttingOptimizationOnline algorithm.iterations=0`
  - Description: the **online (closed-loop)** version — the agent is told about a 0.8 m scrap
    segment only when it is within `reveal_lead` m of the cut line, decides each cut with only the
    visible past, and is scored against the full hidden defect set. An online agent cannot reach
    the clairvoyant optimum (info asymmetry), so it is genuinely harder than the offline task.
