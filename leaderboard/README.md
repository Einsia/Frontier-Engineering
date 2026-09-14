# Leaderboard & Medal Score

Released score artifacts for the Frontier-Eng `v1` set (Experiment 1: foundation
models under `openevolve`, 100 iterations, same initial programs and frozen
verifiers; `gpt-5.4` uses its full 47-task retest).

| File | Contents |
|---|---|
| `medal_podium.csv` | Frozen per-task **gold / silver / bronze** threshold scores and the model that set each. |
| `medal_leaderboard.csv` | Per-model normalized **Medal Score** on v1 and v1-lite, with gold/silver/bronze counts. |
| `exp1_models_raw.csv` | Best-feasible score of each model on each of the 47 tasks (higher is better); source of the podium. |
| `score_submission.py` | Scores a new submission against the frozen podium. |
| `submission_example.csv` | Example submission (claude-opus-4.6) — scoring it reproduces its leaderboard line. |

## Medal Score

On each task the top-3 best scores in the **v1 snapshot (2026-04-14)** are frozen
as peer baselines — gold (1st), silver (2nd), bronze (3rd). A model earns
**1.00** for reaching the gold score, **0.67** for silver, **0.33** for bronze,
otherwise 0; its Medal Score is the **mean** of this credit over a task set
(normalized to `[0,1]`). It credits only reaching each task's frontier (the
podium) and ignores negligible margins in the long tail — a fairer aggregate
than crediting every ordinal rank when the question is "how often does a model
reach the best-known solutions?" We report it on both the full **v1** set
(47 tasks) and the **v1-lite** subset (10 tasks). (Average rank and other
diagnostics are on the [website leaderboard](https://lab.einsia.ai/frontier-eng/leaderboard).)

> `gpt-oss-120b` is part of the paper's 9-model rank tables, but its per-task raw
> scores were not retained; the released podium is therefore computed over the 8
> models with available raw scores.

## Medal leaderboard (normalized; gold/silver/bronze counts are for v1)

| Rank | Model | Medal (v1) | Medal (v1-lite) | 🥇 | 🥈 | 🥉 |
| :--: | :--- | --: | --: | --: | --: | --: |
| 1 | claude-opus-4.6 | 0.533 | 0.501 | 14 | 15 | 3 |
| 2 | gpt-5.4 | 0.454 | 0.267 | 18 | 4 | 2 |
| 3 | glm-5 | 0.347 | 0.300 | 7 | 8 | 12 |
| 4 | gemini-3.1-pro-preview | 0.277 | 0.267 | 7 | 7 | 4 |
| 5 | deepseek-v3.2 | 0.269 | 0.299 | 6 | 6 | 8 |
| 6 | grok-4.20 | 0.227 | 0.200 | 6 | 5 | 4 |
| 7 | seed-2.0-pro | 0.206 | 0.100 | 6 | 4 | 3 |
| 8 | qwen3-coder-next | 0.170 | 0.066 | 5 | 3 | 3 |

## Score your own model

Put your model's best score per task in a CSV (`Task,Score`, one row per task,
task names as in `medal_podium.csv`), then:

```bash
python leaderboard/score_submission.py your_scores.csv
# -> Medal Score (v1, 47 tasks)      : 0.xxx  (gold .., silver .., bronze ..)
#    Medal Score (v1-lite, 10 tasks) : 0.xxx
```

Sanity check (reproduces claude-opus-4.6's line, 0.533 / 0.501):

```bash
python leaderboard/score_submission.py leaderboard/submission_example.csv
```

Interactive view: [lab.einsia.ai/frontier-eng/leaderboard](https://lab.einsia.ai/frontier-eng/leaderboard)
