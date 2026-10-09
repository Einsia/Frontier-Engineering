# Task 04: Quantum Error Decoder

Navigation document for this task. For the task definition (goal, I/O, scoring) see
[TASK.md](TASK.md).

## Goal

Decode a rotated surface-code memory experiment: turn a syndrome batch plus a graphlike detector
error model into logical-observable predictions, and score against minimum-weight perfect
matching (MWPM). Matching MWPM is 1.0; beating it is above 1.0; ignoring the syndrome is 0.0.

## Files

- `baseline/solution.py`: the evolve entrypoint. The shipped baseline never predicts a flip and
  scores 0.0 by construction. Only the region between `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END`
  is editable.
- `verification/evaluate.py`: evaluation entrypoint. Builds and samples the regimes with Stim,
  recomputes the MWPM anchor, runs the candidate in a separate interpreter, and writes
  `metrics.json`, `artifacts.json` and `eval_report.json`.
- `verification/candidate_runner.py`: the isolated interpreter that loads the candidate. It
  receives only the error model and the syndromes, and refuses `stim`/`pymatching` imports.
- `verification/requirements.txt`: evaluator dependencies (pinned).
- `references/known_best.md`: measured anchors and calibration points.
- `frontier_eval/`: unified-task metadata.
- `TASK.md`, `TASK_zh-CN.md`: task contract (English / Chinese).

## Environment

The decoder itself needs only NumPy (SciPy is allowed). The **evaluator** needs Stim and
PyMatching, which are not part of the default framework runtimes:

```bash
pip install -r benchmarks/QuantumComputing/task_04_quantum_error_decoder/verification/requirements.txt
```

The pins matter. Stim's seeded sampling stream is not stable across versions, so a different
Stim moves the trivial and MWPM references by roughly 1-2% of score, and Stim 1.13 wheels exist
for CPython 3.8-3.12 (`stim>=1.15` is required for 3.13). `frontier-v1-main` is built on
Python 3.12 and already lists this task's requirements file, so the standard bootstrap covers it:

```bash
bash scripts/env/setup_v1_task_envs.sh
```

## Quick Run

From this task directory:

```bash
python verification/evaluate.py --candidate baseline/solution.py
```

Optional arguments:

- `--metrics-out <path>`: metrics JSON for the unified harness (default `metrics.json`).
- `--artifacts-out <path>`: diagnostics JSON (default `artifacts.json`).
- `--report-out <path>`: full human-readable report (default `eval_report.json`).

The shipped baseline prints `combined_score=0.0000 valid=1`.

## Unified Run

From the repository root:

```bash
python -m frontier_eval task=unified \
  task.benchmark=QuantumComputing/task_04_quantum_error_decoder \
  task.runtime.python_path=uv-env:frontier-v1-main \
  algorithm=openevolve algorithm.iterations=0
```

## Sealing an Evaluation

The development seeds are fixed so that scores are comparable across runs, which also means a
candidate can be tuned against those specific shot sets. For a fresh, unpredictable evaluation,
override the seeds; the anchor is recomputed on the new shots, so the normalisation stays valid:

```bash
QEC_DEV_SEED=$RANDOM QEC_SEALED_SEED=$RANDOM \
  python verification/evaluate.py --candidate baseline/solution.py
```

`QEC_CANDIDATE_TIMEOUT_S` (default 240) bounds the candidate subprocess.

## Known Limitations

Stated plainly, because they bound what a score here means:

- **Throughput is part of the score.** The candidate runs inside a wall-clock budget. A
  competent decoder that does not vectorise across shots times out and scores nothing, so a
  slower machine can cost score on an otherwise identical decoder.
- **The 0 -> 1 range is largely reproduction.** Reaching 1.0 means matching a well-documented
  baseline (MWPM). Only scores above 1.0 represent work at the frontier, and such a result
  should be re-confirmed on a fresh unseeded shot set.
- **Cross-platform drift.** Stim's seeded samplers and matcher are not bit-identical across
  architectures; absolute error rates move by a few percent between machines. Scores stay
  self-consistent because the anchor is recomputed from the same shots in the same run.
- **The solved interval is open-ended above 1.0.** Known better-than-MWPM decoders exist, but
  a candidate cannot be verified against a published number the way the MWPM anchor can.