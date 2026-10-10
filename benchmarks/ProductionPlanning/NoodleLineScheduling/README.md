# Frontier-Engineering task package

This task is a deterministic industrial planning benchmark with an executable
verifier. The candidate edits `scripts/init.py`; all input data and scoring
code are protected. The fixture is redistributed from the public Terminal-Bench
task package listed in `references/source.txt`.

Run the local check from this directory:

```bash
python verification/evaluator.py scripts/init.py
```

The evaluator recomputes feasibility and the raw task score from the input data.
It does not trust a score reported by the candidate.
