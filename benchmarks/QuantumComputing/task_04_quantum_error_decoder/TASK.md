# Task 04: Quantum Error Decoder (Rotated Surface Code)

## Goal

Write the classical decoder that a fault-tolerant quantum computer would run in its control
loop. Given a graphlike detector error model and a batch of syndrome bitstrings sampled from a
rotated surface-code memory experiment, predict the logical observable flips.

Decoder quality sets the logical error rate and therefore the physical-qubit overhead of any
useful algorithm. Minimum-weight perfect matching (MWPM) has been the community reference for
two decades, but it is not optimal: it decomposes the error model into a graph and discards the
X/Z correlations that circuit-level depolarizing noise actually creates. Correlated matching,
belief propagation with ordered-statistics post-processing, tensor-network decoders and learned
decoders have all reported lower logical error rates. **Beating MWPM is a live research
frontier, so the score is uncapped: matching MWPM is 1.0, beating it is above 1.0.**

## Editable Scope

- Only edit `baseline/solution.py`.

## Input / Output Interface

`baseline/solution.py` must provide:

```python
def decode(problem, detection_events):
    """Predict logical observable flips from syndrome data."""
```

`problem` describes one memory experiment:

- `num_detectors`, `num_observables`, `distance`, `rounds`;
- `errors`: the **graphlike detector error model**, a list of independent error mechanisms.
  Each entry is `{"p": float, "dets": [int, ...], "obs": [int, ...]}` where `p` is that
  mechanism's independent firing probability, `dets` is the set of detectors it flips (at most
  two, because the model is decomposed), and `obs` is the set of logical observables it flips.

`detection_events` is a boolean array of shape `(shots, num_detectors)`: for each shot, which
detectors fired. A detector is a parity check between stabilizer measurements across rounds, so
a single physical fault typically lights up two detectors -- the endpoints of an error chain.

Return an array of shape `(shots, num_observables)` with 0/1 entries: for each shot, whether you
believe each logical observable was flipped. Entries may be `bool`, integer, or float restricted
to exactly `0.0`/`1.0`.

The true observable flips are never revealed to you. The only evidence is the error model and
the syndrome.

## Evaluation Pipeline

For each regime the evaluator:

1. Builds a rotated surface-code memory circuit with Stim at the regime's `(distance, noise)`.
2. Samples `shots` syndromes with a fixed seed, and keeps the true observable flips aside.
3. Recomputes the MWPM reference (PyMatching 2) on the same decomposed error model and the same
   shots, so the anchor cannot drift from the scored data.
4. Hands your decoder only the error model and the syndrome batch -- in a separate interpreter.
5. Scores your predictions against the true flips.

## Cost and Score

Per regime, with logical error rate `L`:

```text
score = ( log L_trivial - log L_candidate ) / ( log L_trivial - log L_mwpm )
```

- `L_trivial` is the rate of the decoder that never predicts a flip. Scoring 0 means you did no
  better than ignoring the syndrome, and a decoder that *introduces* logical errors is floored
  at 0.
- `L_mwpm` is minimum-weight perfect matching on the same decomposed error model. Reaching it
  scores 1.0.
- There is **no upper clamp**: a decoder genuinely better than matching scores above 1.0.

`combined_score` is the mean over the four development regimes (the value the search maximizes).
Two further regimes at noise strengths absent from the development set are scored separately and
reported as `robustness_score`; they never enter `combined_score` and are not returned to the
search state.

A run in which any development regime is invalid (wrong shape, non-binary entries, a raised
exception, a forbidden import, or a timeout) reports `combined_score = 0.0` with `valid = 0.0`,
and keeps the per-regime reason in `artifacts.json`.

## Regimes

Development regimes at the shipped difficulty level (`DIFFICULTY = 1` in
`verification/evaluate.py`):

| Regime | distance | noise | shots | detectors |
|---|---:|---:|---:|---:|
| `d3_p0.005` | 3 | 0.005 | 6000 | 24 |
| `d5_p0.005` | 5 | 0.005 | 6000 | 120 |
| `d5_p0.010` | 5 | 0.010 | 6000 | 120 |
| `d7_p0.005` | 7 | 0.005 | 6000 | 336 |

Sealed regimes (reported as `robustness_score`):

| Regime | distance | noise | shots | detectors |
|---|---:|---:|---:|---:|
| `sealed_d5_p0.007` | 5 | 0.007 | 4000 | 120 |
| `sealed_d7_p0.008` | 7 | 0.008 | 4000 | 336 |

Do not hardcode these: every regime hands you its own `distance`, `rounds`, `num_detectors`,
`num_observables` and decomposed `errors`, and the shot count is the first axis of
`detection_events`. A decoder that reads its geometry from the problem works at every level; one
that assumes `d=3` does not.

## Budget Your Decoding Time

At the shipped level you are handed 6000 shots per development regime and 4000 per sealed
regime, and the candidate subprocess must finish inside `QEC_CANDIDATE_TIMEOUT_S` (240 s by
default) within a 300 s harness budget.

A per-shot Python loop that recomputes shortest paths will not finish. Precompute whatever
depends only on the error model once per regime, and vectorise across shots where you can. **A
correct decoder that times out scores nothing.**

## Constraints

1. Deterministic CPU code, Python standard library + NumPy + SciPy only.
2. Importing `stim` or `pymatching` is an invalid submission: the reference decoder is the
   anchor, not the answer. The evaluator refuses those imports while your decoder runs and
   rejects a module that has already bound either one.
3. The syndrome batch is the only evidence. The true flips are never handed to your process.
4. Do not read `verification/` or `frontier_eval/`.

## Reproduce

```bash
python verification/evaluate.py --candidate baseline/solution.py
```

Framework compatibility:

```bash
python -m frontier_eval task=unified task.benchmark=QuantumComputing/task_04_quantum_error_decoder \
  task.runtime.python_path=uv-env:frontier-v1-main algorithm=openevolve algorithm.iterations=0
```