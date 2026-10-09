# QuantumErrorDecoder -- known values and provenance

## Provenance

This task is ported from the `optimization` branch of **ScientistsLastExam**
(`benchmarks/Physics/QuantumErrorDecoder`), where it is registered as a `flagship`/T3
optimization task under the domain `QuantumErrorCorrection`. The circuit-level scoring design,
the difficulty ladder and the calibration points below come from that implementation. The
evaluator here is a re-implementation against the Frontier-Eng unified contract: the candidate
runs in a separate interpreter, sample seeds are injectable, and the output schema is
`metrics.json` / `artifacts.json`.

## Anchors

Re-measured for this port with `stim==1.13.0`, `pymatching==2.4.0`, `numpy 1.26.4` on CPython
3.11 (Windows x86-64), on the regression seeds declared in `verification/evaluate.py`
(`QEC_DEV_SEED=20260807`, `QEC_SEALED_SEED=771103`):

| Regime | shots | detectors | trivial LER | MWPM LER (anchor = 1.0) |
|---|---:|---:|---:|---:|
| `d3_p0.005` | 6000 | 24 | 0.105333 | 0.014833 |
| `d5_p0.005` | 6000 | 120 | 0.230000 | 0.014333 |
| `d5_p0.010` | 6000 | 120 | 0.341333 | 0.083333 |
| `d7_p0.005` | 6000 | 336 | 0.350667 | 0.009667 |
| `sealed_d5_p0.007` | 4000 | 120 | 0.272500 | 0.036000 |
| `sealed_d7_p0.008` | 4000 | 336 | 0.426750 | 0.059250 |

`d` is the code distance (with `d` rounds) and `p` is the uniform circuit-level noise strength.
The anchor is recomputed at evaluation time by PyMatching on the same decomposed detector error
model and the same shots, so it cannot drift from the scored shot set.

The upstream task reports slightly different absolute rates on its own host (Linux, Python 3.8,
`numpy 1.24.4`); for example `d3_p0.005` is 0.10700 trivial / 0.01750 MWPM there. The gap is a
few percent of error rate and comes from Stim's seeded samplers not being bit-identical across
platforms, not from a different definition. Because the score is a ratio of logarithms taken
within one run, this drift does not bias a comparison between two candidates measured on the
same machine, but absolute numbers should not be compared across machines.

## Score scale

Verified directly against the shipped evaluator on `d5_p0.010`
(trivial LER 0.341333, MWPM LER 0.083333), by scoring crafted prediction arrays:

| Prediction | logical error rate | score |
|---|---:|---:|
| Never predict a flip (shipped baseline) | 0.341333 | **0.0000** |
| MWPM anchor | 0.083333 | **1.0000** |
| Oracle on 25% of shots, no flip elsewhere | 0.254500 | 0.2082 |
| Oracle on 50% of shots | 0.176333 | 0.4684 |
| Oracle on 75% of shots | 0.083500 | 0.9986 |
| Truth (not reachable by a candidate) | 0.000000 | **5.8991** |

The scale is therefore continuous between 0 and 1, reaches exactly 1.0 at the anchor, and is not
clamped above -- which is what lets a better-than-MWPM decoder be represented. The truth row is
a probe of the metric only; a candidate never receives the observable flips.

## Calibration points

Reported by the upstream task for the same regime set (`combined_score`; not re-measured here):

| Decoder | combined_score |
|---|---:|
| Shipped baseline -- never predict a flip | 0.0000 |
| NumPy/SciPy greedy matching | 0.2395 |
| NumPy/SciPy assignment-reduction matching | 0.3832 |
| A single budget-one GPT-5.6 draw | 0.7391 |
| PyMatching 2 MWPM | 1.0000 (by definition) |
| Published sub-matching decoders | > 1.0 |

The two NumPy/SciPy references matter for fairness: candidates may use only the standard library,
NumPy and SciPy, while the anchor is a specialist C++ matching library. Both references were
written under the candidate constraints and stay below 1.0, so the gap to the anchor is an
implementation-quality gap rather than an impossibility.

## Difficulty levels

`DIFFICULTY` in `verification/evaluate.py` selects the regime set. Level 1 is shipped; the ladder
is an explicit measured table and a level with no entry raises rather than being extrapolated.

| Level | development regimes | shots |
|---:|---|---:|
| 1 | `(3,0.005) (5,0.005) (5,0.010) (7,0.005)` | 6000 |
| 2 | `(5,0.008) (7,0.008) (7,0.012) (9,0.008)` | 2400 |
| 3 | `(7,0.010) (9,0.010) (9,0.012) (11,0.010)` | 1200 |

Shot counts hold the decoding workload fixed rather than the shot count: work is shots times the
summed detector count, and detectors grow as `d^2` (24, 120, 336, 720, 1320 for `d` = 3, 5, 7, 9,
11). Raising the level therefore makes instances fewer but larger instead of making the task
longer to run.

## Why the score is uncapped

Minimum-weight perfect matching is the community reference, not the optimum. It decomposes the
circuit-level error model into a graph and therefore discards X/Z correlations that circuit-level
depolarizing noise actually produces. Decoders reported to beat matching on surface-code memory
include correlated/hierarchical matching, belief propagation with ordered-statistics
post-processing, tensor-network decoders, and learned decoders; Bausch et al.,
DOI `10.1038/s41586-024-08148-8`, report a recurrent-transformer decoder below both matching and
correlated matching on Google's distance-3 and distance-5 experimental data.

## Citations

- Gidney, "Stim: a fast stabilizer circuit simulator", Quantum 5, 497 (2021).
- Higgott & Gidney, "Sparse Blossom: correcting a million errors per core second with minimum-weight matching", Quantum 9, 1600 (2025).
- Google Quantum AI, "Suppressing quantum errors by scaling a surface code logical qubit", Nature 614, 676 (2023).