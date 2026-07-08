# PCR Primer Design Optimization

## 1. Problem

Design a pair of PCR primers (forward and reverse) for a synthetic DNA template.
The primers must specifically amplify the target amplicon region while satisfying
thermodynamic and structural constraints.

Primer design is critical for successful PCR amplification. Poorly designed
primers can lead to non-specific amplification, primer-dimer artifacts, or failed
reactions.

## 2. Template and Amplicon

The template sequence is a 120 bp synthetic DNA fragment:

```text
AAGTAAAGGCTAGTGCCCGACAAAGCGATTGTTGGGATTGTACTTGTCGGCAACGTTCCAAACG
TATGGAGGACGGGTAACGTCGGGCTAATGAATTAAGGAGCATGTAGTGCGCAGAGA
```

- **Amplicon start**: index 20 (0-based)
- **Amplicon end**: index 99 (0-based, inclusive)
- **Amplicon length**: 80 bp

The forward primer must bind to the forward strand at the start of the amplicon.
The reverse primer must bind to the reverse-complement of the template strand at
the end of the amplicon.

## 3. Decision Variables

Submit two DNA sequences:

- `forward_primer`: the forward primer sequence (5'' → 3'')
- `reverse_primer`: the reverse primer sequence (5'' → 3'')

Each primer must satisfy the following constraints:

| Constraint | Range |
|---|---|
| Length | 18–25 bp |
| GC content | 40–60% |
| Melting temperature (Tm) | 50–58°C |
| Max Tm difference between primers | ≤ 3°C |
| GC clamp (G/C in last 5 bases) | At least 1, at most 4 |
| Self-complementarity | ≤ 6 bp contiguous match |
| Pair complementarity | ≤ 6 bp contiguous match |
| Hairpin stem | ≤ 8 bp |
| Max homopolymer run | ≤ 4 identical bases |
| Alignment | Primers must align to the intended amplicon boundaries |
| Product length | PCR product length must be between 1 and template length |

## 4. Thermodynamic Model

Melting temperature is computed using the nearest-neighbor thermodynamic model
with SantaLucia salt correction:

```text
Tm = (1000 * ΔH) / (ΔS + R * ln(C) + salt_correction) - 273.15
```

- Nearest-neighbor parameters from Breslauer et al. (1986)
- Salt correction: SantaLucia (1998) formula
- Monovalent cation: 50 mM
- Divalent cation: 2 mM
- dNTP concentration: 0.8 mM
- DNA concentration: 50 nM

## 5. Submission Format

Write `submission.json` in the working directory:

```json
{
  "forward_primer": "CAAAGCGATTGTTGGGATTG",
  "reverse_primer": "CTTAATTCATTAGCCCGACG"
}
```

Both keys are required. Each sequence must be an uppercase DNA string consisting only of
the characters A, T, C, and G.

## 6. Hard Validation Gates

Hard validation gates determine feasibility. A submission that violates any gate
receives a final score of zero regardless of metric quality. The evaluator applies
10 hard validation gates; some gates check multiple conditions.

**Gate 1 — Character validity**
- Fail if any primer contains characters other than A, T, C, G.

**Gate 2 — Primer length**
- Fail if either primer is shorter than the minimum length (18 bp).
- Fail if either primer is longer than the maximum length (25 bp).

**Gate 3 — GC content**
- Fail if either primer GC content is below the minimum (40%).
- Fail if either primer GC content exceeds the maximum (60%).

**Gate 4 — Melting temperature**
- Fail if either primer Tm is outside the acceptable range (50–58°C).
- Fail if the absolute Tm difference between primers exceeds the limit (3°C).

**Gate 5 — GC clamp**
- Fail if any primer has fewer than 1 or more than 4 G/C bases in its last 5 bases (3′ end).

**Gate 6 — Self- and pair complementarity**
- Fail if any primer has a contiguous self-complementary match exceeding 6 bp.
- Fail if the forward and reverse primers have a contiguous cross-dimer match exceeding 6 bp.

**Gate 7 — Hairpin structure**
- Fail if any primer forms a hairpin stem longer than 8 bp.

**Gate 8 — Homopolymer run**
- Fail if any primer contains a run of 5 or more identical bases.

**Gate 9 — Alignment specificity**
- Fail if the forward primer does not align to the start of the amplicon region.
- Fail if the reverse primer does not align (as reverse complement) to the end of the amplicon region.

**Gate 10 — Product length**
- Fail if the estimated PCR product length is outside the range [1, template length].

Infeasible submissions receive a final score of `0.0`.

## 7. Quality Metrics

The evaluator computes ten normalised quality sub-scores, each in [0, 1]:

| # | Metric | Quality target |
|---|---|---|
| 1 | length_score | 20-22 bp |
| 2 | gc_content_score | 50% |
| 3 | tm_score | proximity to optimum (55°C) |
| 4 | gc_clamp_score | G/C fraction in last 3 bases |
| 5 | self_complementarity_score | 0 bp complementarity |
| 6 | pair_complementarity_score | 0 bp cross-dimer complementarity |
| 7 | repeat_score | 0 bp internal repeats |
| 8 | hairpin_score | 0 bp hairpin stem |
| 9 | mononucleotide_run_score | 0 bp homopolymer runs |
| 10 | product_length_score | 80-120 bp product length |

Hard validation gates (Section 6) determine feasibility. Quality metrics (Section 7)
evaluate and rank feasible submissions.

The composite final score is:

```text
final_score = sum (weight_i * metric_sub_score_i)
```

Higher final score is better.
## 8. Evaluation

### Evaluate a produced submission

```bash
python verification/evaluator.py --submission submission.json
```

### Run a candidate optimizer script and evaluate its output

```bash
python verification/evaluator.py scripts/init.py
```

## 9. References

- Configuration: `references/primer_config.json`
- Baseline optimizer: `scripts/init.py`
- Baseline solution (GA-based): `baseline/solution.py`
- Evaluator: `verification/evaluator.py`
