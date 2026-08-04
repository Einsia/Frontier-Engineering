# Task: Robust Psychometric Test Assembly

## Background

Operational test assembly must balance measurement quality with content coverage, administration time, fairness risk, item exposure, and test security.

The candidate selects 24 items from a synthetic bank of 80 items while satisfying every hard constraint and improving information across several ability levels.

## Input

The problem JSON contains the required test length, exact domain quotas, ability points and weights, operational limits, and the candidate item bank.

Each item includes an integer ID, domain, content strand, completion time, discrimination, difficulty, synthetic DIF risk, exposure, and an optional enemy group.

Scenario names, random seeds, and feedback labels are removed before the problem is passed to the candidate.

## Output

The candidate must write a JSON object containing an integer list named `selected_ids`.

Example: `{"selected_ids": [1, 2, 3]}`

## Hard constraints

1. Select exactly `test_length` items.
2. Use only known item IDs and do not repeat an ID.
3. Match every value in `domain_targets` exactly.
4. Do not exceed `max_items_per_enemy_group`.
5. Do not exceed `max_total_time`.
6. Do not exceed `max_mean_dif`.
7. Do not exceed `max_mean_exposure`.
8. Finish within the evaluator time limit.

## Measurement information

The benchmark uses a simplified two-parameter logistic model.

`P(theta) = 1 / (1 + exp(-a * (theta - b)))`

`I(theta) = a^2 * P(theta) * (1 - P(theta))`

The evaluator computes the mean selected-item information at four ability points.

## Scoring

The raw objective combines weighted information, worst-point information, profile balance, DIF quality, exposure quality, time efficiency, and content-strand coverage.

The frozen initial solution defines 50 points in every scenario. Better solutions score above 50 and worse solutions score below 50.

The final robust score is 75 percent mean scenario score and 25 percent twentieth-percentile scenario score.

If any scenario violates a hard constraint, the formal combined score is zero. A diagnostic score is still returned.

## Scenarios

The evaluator contains six development scenarios and four validation scenarios.

Scenarios vary domain quotas, ability-profile weights, time limits, DIF limits, and exposure limits. Fixed seeds make every run reproducible.

## Runtime

The candidate must be deterministic, self-contained, and offline. Each scenario has a 10-second candidate timeout.

The benchmark uses only the Python standard library and requires no GPU, external dataset, network access, or API key.

## Scope

All item banks and risk indicators are synthetic. The benchmark evaluates optimization and constraint handling; it does not validate the reliability, validity, fairness, clinical utility, or legal compliance of a real assessment.
