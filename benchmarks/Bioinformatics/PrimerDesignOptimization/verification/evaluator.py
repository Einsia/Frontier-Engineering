"""Evaluator for PCR Primer Design Optimization.

Evaluates primer pairs designed by scripts/init.py (or a candidate program)
against thermodynamic, structural, and specificity criteria defined in
references/primer_config.json.

Usage
-----
    python verification/evaluator.py --submission submission.json
    python verification/evaluator.py scripts/init.py

Frozen Spec v2.0 sections referenced throughout.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

_COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Config  (Spec §1)                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def load_config() -> dict[str, Any]:
    """Load primer_config.json from the references/ directory.

    Returns
    -------
    dict
        Full configuration including template, constraints, scoring weights,
        thermodynamic parameters, and optimisation settings.

    Spec
    ----
    §1.1 — Benchmark configuration schema.
    """
    config_path = Path(__file__).resolve().parent.parent / "references" / "primer_config.json"
    with open(config_path, encoding="utf-8") as fh:
        return json.load(fh)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Utilities  (Spec §2)                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Common helper functions used across thermodynamic, validation, and metric modules.

def compute_self_complementarity(seq: str) -> int:
    """Maximum contiguous 3''-end self-complementarity.

    Checks every substring of *seq* (length >= 3) for presence in its own
    reverse complement.  The result is 3''-end biased.

    Parameters
    ----------
    seq : str
        Primer sequence.

    Returns
    -------
    int
        Length of the longest self-complementary substring.

    Spec
    ----
    """
    rc = reverse_complement(seq)
    seq_u = seq.upper()
    rc_u = rc.upper()
    best = 0
    for i in range(len(seq_u) - 2):
        for j in range(i + 3, len(seq_u) + 1):
            sub = seq_u[i:j]
            if sub in rc_u:
                best = max(best, len(sub))
    return best

def reverse_complement(seq: str) -> str:
    """Return the reverse complement of a DNA sequence.

    Parameters
    ----------
    seq : str
        Uppercase DNA string (A, T, C, G).

    Returns
    -------
    str
        Reverse complement (5'' → 3'').

    Spec
    ----
    §2.1 — Sequence manipulation primitives.
    """
    return "".join(_COMPLEMENT.get(base, base) for base in reversed(seq))

def canonical_pair_key(dimer: str) -> str:
    """Construct the canonical key ``"{dimer}/{complement}"`` for NN table lookup.

    The key format is ``{5''-dimer}/{3''-complement}``, where the complement
    is the Watson–Crick pairing of each base without reversal.

    Parameters
    ----------
    dimer : str
        Two-base DNA string (5'' → 3'').

    Returns
    -------
    str
        Key string of the form ``"XX/YY"``.  The caller should use
        ``lookup_nn_parameter()`` to resolve it against the parameter table.

    Spec
    ----
    §2.2 — Nearest-neighbour parameter lookup convention.
    """
    return dimer + "/" + "".join(_COMPLEMENT[b] for b in dimer)

def lookup_nn_parameter(dimer: str, table: dict[str, float]) -> float:
    """Look up a nearest-neighbour parameter value with reverse-complement fallback.

    Constructs the canonical key via ``canonical_pair_key(dimer)``.  If that key
    is not present in *table* (covering only 10 of 16 possible dimer combinations),
    falls back to the reverse-complement orientation, which is guaranteed to exist
    for all 16 dinucleotide combinations by NN symmetry.

    Parameters
    ----------
    dimer : str
        Two-base DNA string (5'' → 3'').
    table : dict[str, float]
        NN parameter dictionary (``enthalpy_kcal`` or ``entropy_cal``).

    Returns
    -------
    float
        The parameter value for the resolved dimer pair.

    Spec
    ----
    §2.3 — NN parameter resolution with symmetry fallback.
    """
    key = canonical_pair_key(dimer)
    if key not in table:
        rc = "".join(_COMPLEMENT[b] for b in reversed(dimer))
        key = canonical_pair_key(rc)
    return table[key]

def is_valid_dna(seq: str) -> bool:
    """Check whether a string consists only of A, T, C, G.

    Parameters
    ----------
    seq : str
        Candidate DNA string.

    Returns
    -------
    bool

    Spec
    ----
    §2.3 — Character-set validation helper.
    """
    if not seq:
        return False
    return all(base in "ATCGatcg" for base in seq)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Thermodynamics  (Spec §3)                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Deterministic nearest-neighbour thermodynamics (SantaLucia 1998 / Breslauer 1986).

def compute_nn_enthalpy(seq: str, cfg: dict[str, Any]) -> float:
    """Total nearest-neighbour enthalpy ΔH (kcal/mol) for a DNA duplex.

    Parameters
    ----------
    seq : str
        Primer-length DNA sequence (18–25 bp).
    cfg : dict
        Benchmark configuration (provides NN enthalpy table).

    Returns
    -------
    float
        Sum of nearest-neighbour enthalpy contributions plus initiation
        and terminal penalties.

    Spec
    ----
    §3.1 — Nearest-neighbour enthalpy.
    """
    seq = seq.upper()
    enthalpy = cfg["thermodynamic"]["nearest_neighbor_params"]["enthalpy_kcal"]
    dh = 0.0
    for i in range(len(seq) - 1):
        dimer = seq[i : i + 2]
        dh += lookup_nn_parameter(dimer, enthalpy)
    dh += 0.2
    if seq[0] in "AT":
        dh += 2.3
    if seq[-1] in "AT":
        dh += 2.3
    return dh

def compute_nn_entropy(seq: str, cfg: dict[str, Any]) -> float:
    """Total nearest-neighbour entropy ΔS (cal/mol·K) for a DNA duplex.

    Parameters
    ----------
    seq : str
        Primer-length DNA sequence (18–25 bp).
    cfg : dict
        Benchmark configuration (provides NN entropy table).

    Returns
    -------
    float
        Sum of nearest-neighbour entropy contributions plus initiation
        and terminal penalties.

    Spec
    ----
    §3.2 — Nearest-neighbour entropy.
    """
    seq = seq.upper()
    entropy = cfg["thermodynamic"]["nearest_neighbor_params"]["entropy_cal"]
    ds = 0.0
    for i in range(len(seq) - 1):
        dimer = seq[i : i + 2]
        ds += lookup_nn_parameter(dimer, entropy)
    ds += -5.7
    if seq[0] in "AT":
        ds += 4.1
    if seq[-1] in "AT":
        ds += 4.1
    return ds

def salt_correction(seq_len: int, cfg: dict[str, Any]) -> float:
    """SantaLucia salt correction term for melting temperature.

    Parameters
    ----------
    seq_len : int
        Length of the primer in bases.
    cfg : dict
        Benchmark configuration (ion concentrations).

    Returns
    -------
    float
        Correction term added to the denominator before the Tm formula.

    Spec
    ----
    §3.3 — Salt correction (SantaLucia 1998).
    """
    thermo = cfg["thermodynamic"]
    na = thermo["monovalent_cation_concentration"]
    mg = thermo["divalent_cation_concentration"]
    dntp = thermo["dntp_concentration"]
    na_eq = na + 3.7 * math.sqrt(max(0.0, mg - dntp))
    return 0.368 * (seq_len - 1) * math.log(na_eq / 1000.0)

def compute_tm(seq: str, cfg: dict[str, Any]) -> float:
    """Melting temperature Tm (°C) using the nearest-neighbour model.

    Tm = (1000·ΔH) / (ΔS + R·ln(C) + salt_correction) − 273.15

    Parameters
    ----------
    seq : str
        Primer-length DNA sequence.
    cfg : dict
        Benchmark configuration.

    Returns
    -------
    float
        Tm in degrees Celsius, rounded to two decimal places.

    Spec
    ----
    §3.4 — Melting temperature (primary thermodynamic metric).
    """
    seq = seq.upper()
    R = 1.987
    dh = compute_nn_enthalpy(seq, cfg)
    ds = compute_nn_entropy(seq, cfg)
    sc = salt_correction(len(seq), cfg)
    dna_conc = cfg["thermodynamic"]["dna_concentration"]
    ct = dna_conc * 1e-9
    tm = (1000.0 * dh) / (ds + R * math.log(ct) + sc) - 273.15
    return round(tm, 2)

def compute_gc_content(seq: str) -> float:
    """GC content as a percentage of total bases.

    Parameters
    ----------
    seq : str
        DNA string.

    Returns
    -------
    float
        GC percentage in [0, 100].  Returns 0.0 for empty input.

    Spec
    ----
    §3.5 — GC content (simple composition metric).
    """
    if not seq:
        return 0.0
    seq = seq.upper()
    gc_count = sum(1 for base in seq if base in "GC")
    return 100.0 * gc_count / len(seq)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Template Alignment  (Spec §4)                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Primer-template alignment and off-target binding (Spec v2.0 §4).

def align_primers(
    fwd: str,
    rev: str,
    template: str,
    amp_start: int,
    amp_end: int,
) -> dict[str, Any]:
    """Align forward and reverse primers to the template.

    The forward primer aligns to the forward strand at the amplicon start.
    The reverse primer aligns (as reverse complement) to the forward strand
    at the amplicon end.

    Parameters
    ----------
    fwd : str
        Forward primer sequence.
    rev : str
        Reverse primer sequence.
    template : str
        Full template sequence.
    amp_start : int
        0-based start index of the amplicon.
    amp_end : int
        0-based inclusive end index of the amplicon.

    Returns
    -------
    dict
        ``{"fwd_start", "fwd_end", "rev_start", "rev_end", "perfect_match"}``
        describing the aligned positions.

    Spec
    ----
    §4.1 — Primer-template alignment.
    """
    fwd_u = fwd.upper()
    rev_u = rev.upper()
    fwd_start = template.upper().find(fwd_u, amp_start)
    if fwd_start == -1:
        fwd_start = template.upper().find(fwd_u)
    fwd_end = fwd_start + len(fwd_u) if fwd_start != -1 else -1

    rev_rc = reverse_complement(rev_u)
    rev_end = template.upper().find(rev_rc, 0, amp_end + len(rev_u))
    if rev_end == -1:
        rev_end = template.upper().find(rev_rc)
    rev_start = rev_end - len(rev_u) + 1 if rev_end != -1 else -1
    if rev_start < 0 and rev_end != -1:
        rev_start = 0

    perfect_match = (
        fwd_start != -1
        and template[fwd_start:fwd_start + len(fwd_u)].upper() == fwd_u
        and rev_end != -1
        and template[rev_end:rev_end + len(rev_rc)].upper() == rev_rc
    )

    return {
        "fwd_start": fwd_start,
        "fwd_end": fwd_end,
        "rev_start": rev_start,
        "rev_end": rev_end,
        "perfect_match": perfect_match,
    }

def count_offtarget_binding(
    primer: str,
    template: str,
    min_homology: int = 7,
) -> int:
    """Count non-target binding sites for a primer on the template.

    Slides the primer along the template and identifies sub-sequences
    with complementarity ≥ ``min_homology`` bases outside the intended
    binding region.

    Parameters
    ----------
    primer : str
        Primer sequence to test.
    template : str
        Full template sequence.
    min_homology : int
        Minimum contiguous match to count as a potential off-target site.

    Returns
    -------
    int
        Number of off-target binding sites found.

    Spec
    ----
    §4.2 — In-silico PCR specificity.
    """
    raise NotImplementedError

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Validation Gates  (Spec §5)                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Hard validation gates (Spec v2.0 §5).
# Any violation sets valid = 0 and combined_score = 0.

def validate_charset(fwd: str, rev: str) -> bool:
    """Check that both primers contain only A, T, C, G.

    Parameters
    ----------
    fwd : str
    rev : str

    Returns
    -------
    bool
        True if both primers contain only valid DNA bases.

    Spec
    ----
    §5.1 — Character set.
    """
    return is_valid_dna(fwd) and is_valid_dna(rev)

def validate_length(fwd: str, rev: str, cfg: dict[str, Any]) -> bool:
    """Check that each primer length is within [min, max].

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    bool
        True if both primer lengths are within bounds.

    Spec
    ----
    §5.2 — Primer length.
    """
    lo = cfg["constraints"]["primer_length"]["min"]
    hi = cfg["constraints"]["primer_length"]["max"]
    return lo <= len(fwd) <= hi and lo <= len(rev) <= hi

def validate_gc_content(fwd: str, rev: str, cfg: dict[str, Any]) -> bool:
    """Check that each primer GC content is within [min, max].

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    bool
        True if both primer GC percentages are within bounds.

    Spec
    ----
    §5.3 — GC content range.
    """
    lo = cfg["constraints"]["gc_content"]["min"]
    hi = cfg["constraints"]["gc_content"]["max"]
    gc_fwd = compute_gc_content(fwd)
    gc_rev = compute_gc_content(rev)
    return lo <= gc_fwd <= hi and lo <= gc_rev <= hi

def validate_tm(fwd: str, rev: str, cfg: dict[str, Any]) -> bool:
    """Check that both Tm values and their difference are within bounds.

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    bool
        True if both Tm values and |Tm_fwd − Tm_rev| pass.

    Spec
    ----
    §5.4 — Melting temperature bounds.
    """
    tm_min = cfg["constraints"]["melting_temperature"]["min"]
    tm_max = cfg["constraints"]["melting_temperature"]["max"]
    tm_diff_max = cfg["constraints"]["tm_difference_max"]
    tm_fwd = compute_tm(fwd, cfg)
    tm_rev = compute_tm(rev, cfg)
    if not (tm_min <= tm_fwd <= tm_max):
        return False
    if not (tm_min <= tm_rev <= tm_max):
        return False
    return abs(tm_fwd - tm_rev) <= tm_diff_max

def validate_gc_clamp(fwd: str, rev: str, cfg: dict[str, Any]) -> bool:
    """Check GC-clamp (G or C in the last 5 bases at the 3' end).

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    bool
        True if both primers satisfy the GC-clamp requirement.

    Spec
    ----
    §5.5 — GC clamp requirement.
    """
    required = cfg["constraints"]["gc_clamp"]["required"]
    if not required:
        return True
    for primer in (fwd, rev):
        last5 = primer[-5:].upper()
        gc_count = sum(1 for base in last5 if base in "GC")
        if gc_count < 1:
            return False
    return True

def validate_self_complementarity(
    fwd: str, rev: str, cfg: dict[str, Any],
) -> bool:
    """Check self- and cross-dimer complementarity limits.

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    bool
        True if all self- and cross-complementarity values are within bounds.

    Spec
    ----
    §5.6 — Self- and cross-complementarity.
    """
    max_self = cfg["constraints"]["self_complementarity_max"]
    max_pair = cfg["constraints"]["pair_complementarity_max"]
    if compute_self_complementarity(fwd) > max_self:
        return False
    if compute_self_complementarity(rev) > max_self:
        return False
    fwd_rc = reverse_complement(fwd)
    rev_rc = reverse_complement(rev)
    fwd_u = fwd.upper()
    rev_u = rev.upper()
    fwd_rc_u = fwd_rc.upper()
    rev_rc_u = rev_rc.upper()
    best_cross = 0
    for i in range(len(fwd_u) - 2):
        for j in range(i + 3, len(fwd_u) + 1):
            sub = fwd_u[i:j]
            if sub in rev_rc_u:
                best_cross = max(best_cross, len(sub))
    if best_cross > max_pair:
        return False
    best_cross_rev = 0
    for i in range(len(rev_u) - 2):
        for j in range(i + 3, len(rev_u) + 1):
            sub = rev_u[i:j]
            if sub in fwd_rc_u:
                best_cross_rev = max(best_cross_rev, len(sub))
    return best_cross_rev <= max_pair

def validate_hairpin(fwd: str, rev: str, cfg: dict[str, Any]) -> bool:
    """Check maximum hairpin stem length for both primers.

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    bool
        True if both primers have hairpin stem length within limits.

    Spec
    ----
    §5.7 — Hairpin structure.
    """
    max_stem = cfg["constraints"]["max_hairpin_stem"]
    for primer in (fwd, rev):
        seq = primer.upper()
        best = 0
        for i in range(len(seq) - 4):
            for j in range(i + 3, len(seq) - 2):
                sub = seq[i:j]
                sub_rc = "".join(_COMPLEMENT[b] for b in reversed(sub))
                if len(sub) < 3:
                    continue
                for k in range(j + 3, len(seq) - len(sub) + 1):
                    candidate = seq[k:k + len(sub)]
                    if candidate == sub_rc:
                        best = max(best, len(sub))
        if best > max_stem:
            return False
    return True

def validate_mononucleotide_run(
    fwd: str, rev: str, cfg: dict[str, Any],
) -> bool:
    """Check that no homopolymer run exceeds max_poly_x_run.

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    bool
        True if neither primer contains an excessive mononucleotide run.

    Spec
    ----
    §5.8 — Homopolymer / mononucleotide runs.
    """
    max_run = cfg["constraints"]["max_poly_x_run"]
    for primer in (fwd, rev):
        best = 1
        run = 1
        seq = primer.upper()
        for i in range(1, len(seq)):
            if seq[i] == seq[i - 1]:
                run += 1
                best = max(best, run)
            else:
                run = 1
        if best > max_run:
            return False
    return True

def validate_alignment(
    fwd: str, rev: str, template: str, amp_start: int, amp_end: int,
) -> bool:
    """Check that primers align specifically to the intended amplicon region.

    Parameters
    ----------
    fwd : str
    rev : str
    template : str
    amp_start : int
    amp_end : int

    Returns
    -------
    bool
        True if both primers align to the expected amplicon boundaries.

    Spec
    ----
    §5.9 — Alignment specificity.
    """
    fwd_u = fwd.upper()
    rev_u = rev.upper()
    tpl_u = template.upper()
    fwd_pos = tpl_u.find(fwd_u, max(0, amp_start - 5))
    if fwd_pos == -1 or fwd_pos > amp_start + 5:
        return False
    rev_rc = reverse_complement(rev_u)
    rev_rc_pos = tpl_u.find(rev_rc, max(0, amp_end - len(rev_rc) - 5))
    if rev_rc_pos == -1:
        return False
    return True

def validate_product_length(
    fwd: str, rev: str, template: str,
) -> bool:
    """Estimate PCR product length from aligned primer positions.

    Parameters
    ----------
    fwd : str
    rev : str
    template : str

    Returns
    -------
    bool
        True if the estimated product length is positive and plausible.

    Spec
    ----
    §5.10 — Product length sanity check.
    """
    fwd_u = fwd.upper()
    rev_u = rev.upper()
    tpl_u = template.upper()
    fwd_pos = tpl_u.find(fwd_u)
    if fwd_pos == -1:
        return False
    rev_rc = reverse_complement(rev_u)
    rev_pos = tpl_u.rfind(rev_rc)
    if rev_pos == -1:
        return False
    prod_len = rev_pos + len(rev_rc) - fwd_pos
    return 1 <= prod_len <= len(template)

def run_hard_gates(
    fwd: str, rev: str, cfg: dict[str, Any],
    template: str, amp_start: int, amp_end: int,
) -> bool:
    """Run every hard validation gate, including template-dependent gates.

    This is the single aggregation point for all hard gates defined in
    Frozen Spec §5.  Short-circuits on the first violation.

    Parameters
    ----------
    fwd : str
        Forward primer sequence.
    rev : str
        Reverse primer sequence.
    cfg : dict
        Benchmark configuration.
    template : str
        Full template sequence (required for §5.9, §5.10).
    amp_start : int
        0-based start index of the amplicon region.
    amp_end : int
        0-based inclusive end index of the amplicon region.

    Returns
    -------
    bool
        True if every hard gate passes; False on the first failure.

    Spec
    ----
    §5.11 — Hard-gate aggregation.
    """
    if not validate_charset(fwd, rev):
        return False
    if not validate_length(fwd, rev, cfg):
        return False
    if not validate_gc_content(fwd, rev, cfg):
        return False
    if not validate_tm(fwd, rev, cfg):
        return False
    if not validate_gc_clamp(fwd, rev, cfg):
        return False
    if not validate_self_complementarity(fwd, rev, cfg):
        return False
    if not validate_hairpin(fwd, rev, cfg):
        return False
    if not validate_mononucleotide_run(fwd, rev, cfg):
        return False
    if not validate_alignment(fwd, rev, template, amp_start, amp_end):
        return False
    if not validate_product_length(fwd, rev, template):
        return False
    return True

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Metrics  (Spec §6)                                                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def _linear_score(value: float, threshold: float) -> float:
    """Normalised linear penalty in [0, 1].

    Score = 1.0 at 0, decreases linearly to 0.0 at *threshold*.
    Values above *threshold* return 0.0.

    Parameters
    ----------
    value : float
        Raw measurement to penalise.
    threshold : float
        Maximum acceptable value (score reaches 0 here).

    Returns
    -------
    float
        Normalised score in [0, 1].
    """
    return max(0.0, 1.0 - value / threshold)

# Metric sub-scores (Spec v2.0 §6).
# Each returns a value in [0, 100] (higher is better).  Combined via weighted sum.

def length_score(fwd: str, rev: str, cfg: dict[str, Any]) -> float:
    """Primer-length quality score in [0, 1].

    Piecewise-linear function:
    - Score = 1.0 inside the ideal interval [20, 22].
    - Linear ramp from the valid boundary to the ideal boundary.
    - Clamped to [0, 1].

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    float
        Normalised score in [0, 1].

    Spec
    ----
    §6.1 — Length metric.
    """
    lo = cfg["constraints"]["primer_length"]["min"]
    hi = cfg["constraints"]["primer_length"]["max"]
    ideal_lo, ideal_hi = 20, 22

    def _score_one(seq: str) -> float:
        n = len(seq)
        if n < lo or n > hi:
            return 0.0
        if ideal_lo <= n <= ideal_hi:
            return 1.0
        if n < ideal_lo:
            return (n - lo) / (ideal_lo - lo)
        return (hi - n) / (hi - ideal_hi)

    return (_score_one(fwd) + _score_one(rev)) / 2.0

def gc_content_score(fwd: str, rev: str, cfg: dict[str, Any]) -> float:
    """GC-content quality score in [0, 1].

    Symmetric triangular function using constraint bounds from config.
    Score = 1.0 at centre = (gc_min + gc_max) / 2,
    drops linearly to 0.0 at gc_min and gc_max.

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    float
        Normalised score in [0, 1].

    Spec
    ----
    §6.2 — GC content metric.
    """
    gc_min = cfg["constraints"]["gc_content"]["min"]
    gc_max = cfg["constraints"]["gc_content"]["max"]
    centre = (gc_min + gc_max) / 2.0
    radius = (gc_max - gc_min) / 2.0

    gc_fwd = compute_gc_content(fwd)
    gc_rev = compute_gc_content(rev)

    def _triangular(gc_pct: float) -> float:
        return max(0.0, 1.0 - abs(gc_pct - centre) / radius)

    return (_triangular(gc_fwd) + _triangular(gc_rev)) / 2.0

def tm_score(fwd: str, rev: str, cfg: dict[str, Any]) -> float:
    """Melting-temperature quality score in [0, 1].

    Two multiplicative components:
      1. Tm quality  — proximity to optimal Tm (per-primer, then averaged).
      2. Consistency — small |Tm_fwd − Tm_rev|.

    Combined as:  score = quality_avg × consistency.

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    float
        Normalised score in [0, 1].

    Spec
    ----
    §6.3 — Melting temperature metric.
    """
    tm_min = cfg["constraints"]["melting_temperature"]["min"]
    tm_max = cfg["constraints"]["melting_temperature"]["max"]
    tm_opt = cfg["constraints"]["melting_temperature"]["optimal"]
    tm_diff_max = cfg["constraints"]["tm_difference_max"]

    tm_fwd = compute_tm(fwd, cfg)
    tm_rev = compute_tm(rev, cfg)

    # Per-primer quality: linear peak at optimal
    spread = max(tm_opt - tm_min, tm_max - tm_opt)
    def _quality(tm: float) -> float:
        return max(0.0, 1.0 - abs(tm - tm_opt) / spread)

    quality_avg = (_quality(tm_fwd) + _quality(tm_rev)) / 2.0

    # Pair consistency
    delta = abs(tm_fwd - tm_rev)
    consistency = max(0.0, 1.0 - delta / tm_diff_max)

    return quality_avg * consistency

def gc_clamp_score(fwd: str, rev: str, cfg: dict[str, Any]) -> float:
    """GC-clamp quality score in [0, 1].

    Considers only the last 3 nt of each primer (3'' end).
    Score = fraction of G/C within those 3 nt, averaged across both primers.

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    float
        Normalised score in [0, 1].

    Spec
    ----
    §6.4 — GC clamp metric.
    """
    def _clamp_frac(primer: str) -> float:
        last3 = primer[-3:].upper()
        if len(last3) < 3:
            return 0.0
        gc_count = sum(1 for b in last3 if b in "GC")
        return gc_count / 3.0

    return (_clamp_frac(fwd) + _clamp_frac(rev)) / 2.0

def self_complementarity_score(fwd: str, rev: str, cfg: dict[str, Any]) -> float:
    """Self-complementarity quality score in [0, 1].

    Score = 1.0 at 0 bp complementarity, decreases linearly to 0.0
    at self_complementarity_max (from config).

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    float
        Normalised score in [0, 1].

    Spec
    ----
    §6.5 — Self-complementarity metric.
    """
    max_val = cfg["constraints"]["self_complementarity_max"]
    comp_fwd = compute_self_complementarity(fwd)
    comp_rev = compute_self_complementarity(rev)

    return (_linear_score(comp_fwd, max_val) + _linear_score(comp_rev, max_val)) / 2.0

def pair_complementarity_score(fwd: str, rev: str, cfg: dict[str, Any]) -> float:
    """Pair-complementarity (cross-dimer) quality score in [0, 1].

    Score = 1.0 at 0 bp cross-dimer complementarity, decreases linearly
    to 0.0 at pair_complementarity_max (from config).

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    float
        Normalised score in [0, 1].

    Spec
    ----
    §6.6 — Pair-complementarity metric.
    """
    max_val = cfg["constraints"]["pair_complementarity_max"]
    fwd_rc = reverse_complement(fwd)
    rev_rc = reverse_complement(rev)
    fwd_u = fwd.upper()
    rev_u = rev.upper()
    fwd_rc_u = fwd_rc.upper()
    rev_rc_u = rev_rc.upper()

    best = 0
    for i in range(len(fwd_u) - 2):
        for j in range(i + 3, len(fwd_u) + 1):
            sub = fwd_u[i:j]
            if sub in rev_rc_u:
                best = max(best, len(sub))
    for i in range(len(rev_u) - 2):
        for j in range(i + 3, len(rev_u) + 1):
            sub = rev_u[i:j]
            if sub in fwd_rc_u:
                best = max(best, len(sub))

    return max(0.0, 1.0 - best / max_val)

def hairpin_score(fwd: str, rev: str, cfg: dict[str, Any]) -> float:
    """Hairpin-stem quality score in [0, 1].

    Score = 1.0 at 0 bp stem, decreases linearly to 0.0 at
    max_hairpin_stem (from config).

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    float
        Normalised score in [0, 1].

    Spec
    ----
    §6.7 — Hairpin stability metric.
    """
    max_stem = cfg["constraints"]["max_hairpin_stem"]

    def _max_stem(seq: str) -> int:
        s = seq.upper()
        best = 0
        for i in range(len(s) - 4):
            for j in range(i + 3, len(s) - 2):
                sub = s[i:j]
                sub_rc = "".join(_COMPLEMENT[b] for b in reversed(sub))
                if len(sub) < 3:
                    continue
                for k in range(j + 3, len(s) - len(sub) + 1):
                    candidate = s[k:k + len(sub)]
                    if candidate == sub_rc:
                        best = max(best, len(sub))
        return best

    stem_fwd = _max_stem(fwd)
    stem_rev = _max_stem(rev)

    return (_linear_score(stem_fwd, max_stem) + _linear_score(stem_rev, max_stem)) / 2.0

def repeat_score(fwd: str, rev: str, cfg: dict[str, Any]) -> float:
    """Internal-repeat quality score in [0, 1].

    Score = 1.0 at 0 bp repeats, decreases linearly to 0.0 at
    max_repeat_length (from config).  A repeat is a substring that
    appears at least twice in a primer sequence.

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    float
        Normalised score in [0, 1].

    Spec
    ----
    §6.8 — Internal repeat metric.
    """
    max_val = cfg["constraints"]["max_repeat_length"]

    def _max_repeat(seq: str) -> int:
        s = seq.upper()
        best = 0
        for i in range(len(s)):
            for j in range(i + 1, len(s)):
                sub = s[i:j]
                if s.count(sub) >= 2:
                    best = max(best, len(sub))
        return best

    rep_fwd = _max_repeat(fwd)
    rep_rev = _max_repeat(rev)

    return (_linear_score(rep_fwd, max_val) + _linear_score(rep_rev, max_val)) / 2.0

def mononucleotide_run_score(fwd: str, rev: str, cfg: dict[str, Any]) -> float:
    """Homopolymer-run quality score in [0, 1].

    Score = 1.0 at 0 bp run, decreases linearly to 0.0 at
    max_poly_x_run (from config).

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict

    Returns
    -------
    float
        Normalised score in [0, 1].

    Spec
    ----
    §6.9 — Homopolymer run metric.
    """
    max_run = cfg["constraints"]["max_poly_x_run"]

    def _max_run(seq: str) -> int:
        s = seq.upper()
        best = 1
        run = 1
        for i in range(1, len(s)):
            if s[i] == s[i - 1]:
                run += 1
                if run > best:
                    best = run
            else:
                run = 1
        return best

    run_fwd = _max_run(fwd)
    run_rev = _max_run(rev)

    # Shift baseline: a single base is not a run
    # v=1 -> 1.0, v=max_run -> 0.0, linear in between
    def _linear(v: int) -> float:
        if v <= 1:
            return 1.0
        return max(0.0, 1.0 - (v - 1) / (max_run - 1))

    return (_linear(run_fwd) + _linear(run_rev)) / 2.0

def product_length_score(
    fwd: str, rev: str, cfg: dict[str, Any], product_length: int,
) -> float:
    """PCR product-length quality score in [0, 1].

    Plateau + linear-decay function configured by product_length
    preferences in the benchmark config.

    Score = 1.0 inside [preferred_min, preferred_max],
    then linear decay to 0 at the extremes (0 and len(template)).

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict
    product_length : int
        PCR product length in base pairs (computed upstream).

    Returns
    -------
    float
        Normalised score in [0, 1].

    Spec
    ----
    §6.10 — Product length metric.
    """
    product_cfg = cfg.get("product_length", {})
    pref_lo = product_cfg.get("preferred_min", 60)
    pref_hi = product_cfg.get("preferred_max", 150)
    max_len = len(cfg.get("template", {}).get("sequence", ""))

    if product_length <= 0:
        return 0.0
    if pref_lo <= product_length <= pref_hi:
        return 1.0
    if product_length < pref_lo:
        return max(0.0, float(product_length) / pref_lo)
    # product_length > pref_hi
    if max_len > pref_hi:
        return max(0.0, (max_len - product_length) / (max_len - pref_hi))
    return 0.0

# Composite scoring (Spec v2.0 §7).

# 1. Run hard gates.
# 2. If violations exist → combined_score = 0.0, valid = 0.
# 3. Otherwise compute weighted sum of metric sub-scores.
# 4. Return both combined_score and a full score_breakdown.

def compute_score_breakdown(
    fwd: str, rev: str, cfg: dict[str, Any], product_length: int,
) -> dict[str, Any]:
    """Compute all 10 quality metrics and aggregate into a composite score.

    Responsibilities
    ----------------
    1. Compute every metric sub-score by calling each metric function.
    2. Read weights from ``cfg["scoring_weights"]``.
    3. Compute weighted sum and normalise to [0, 1].
    4. Return a detailed breakdown dict.

    This function does NOT perform hard validation, template alignment,
    product-length calculation, or I/O.  It is called by ``evaluate()``
    after validation has passed.

    Parameters
    ----------
    fwd : str
    rev : str
    cfg : dict
    product_length : int
        PCR product length in base pairs (computed upstream by evaluate()).

    Returns
    -------
    dict
        ``{"final_score": float, "sub_scores": dict, "weighted_scores": dict,
          "total_weight": float}``

    Spec
    ----
    §7.1 — Score breakdown computation.
    """
    # --- 1. Compute all 10 metric sub-scores ---
    sub = {}
    sub["length_score"] = length_score(fwd, rev, cfg)
    sub["gc_content_score"] = gc_content_score(fwd, rev, cfg)
    sub["tm_score"] = tm_score(fwd, rev, cfg)
    sub["gc_clamp_score"] = gc_clamp_score(fwd, rev, cfg)
    sub["self_complementarity_score"] = self_complementarity_score(fwd, rev, cfg)
    sub["pair_complementarity_score"] = pair_complementarity_score(fwd, rev, cfg)
    sub["repeat_score"] = repeat_score(fwd, rev, cfg)
    sub["hairpin_score"] = hairpin_score(fwd, rev, cfg)
    sub["mononucleotide_run_score"] = mononucleotide_run_score(fwd, rev, cfg)
    sub["product_length_score"] = product_length_score(fwd, rev, cfg, product_length)

    # --- 2. Read weights from configuration ---
    weights: dict[str, float] = cfg["scoring_weights"]

    # --- 3. Compute weighted scores ---
    weighted: dict[str, float] = {}
    weighted_sum = 0.0
    for key in sub:
        w = weights.get(key, 0.0)
        ws = sub[key] * w
        weighted[key] = round(ws, 8)
        weighted_sum += ws

    total_weight = sum(weights.values())

    # --- 4. Normalise to [0, 1] ---
    if total_weight > 0.0:
        final_score = round(weighted_sum / total_weight, 6)
    else:
        final_score = 0.0

    # --- 5. Clamp for numerical safety ---
    final_score = max(0.0, min(1.0, final_score))

    return {
        "final_score": final_score,
        "sub_scores": sub,
        "weighted_scores": weighted,
        "total_weight": round(total_weight, 4),
    }

def evaluate(
    program_path: str,
    *,
    repo_root: Path | None = None,
    kernel_python: str | None = None,
) -> dict[str, Any]:
    """Full evaluation entrypoint called by frontier_eval/run_eval.py.

    This function is the bridge between the unified benchmark harness and
    the local evaluator.  It:

    1. Locates the submission (either a ``submission.json`` or a candidate
       Python script).
    2. If a script is given, runs it in a temporary directory and captures
       its ``submission.json`` output.
    3. Loads the submission and runs hard gates + metric scoring.
    4. Returns a dict with scores and validation status.

    Parameters
    ----------
    program_path : str
        Path to submission.json or a candidate ``.py`` script.
    repo_root : Path or None
        Repository root (auto-detected if None).
    kernel_python : str or None
        Python interpreter path for running candidate scripts.

    Returns
    -------
    dict
        ``{"final_score": float, "valid": bool, "failure_reason": str,
          "sub_scores": dict, "weighted_scores": dict, "total_weight": float}``

    Spec
    ----
    §7.2 — Evaluation entrypoint (unified harness bridge).
    """
    # --- 1. Resolve paths ---
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    # Resolve candidate path relative to benchmark root first (for scripts),
    # then fall back to repo_root (for harness-provided JSON).
    benchmark_root = Path(__file__).resolve().parent.parent
    program_path_obj = Path(program_path)
    if not program_path_obj.is_absolute():
        candidate = benchmark_root / program_path_obj
        if candidate.exists():
            program_path_obj = candidate
        else:
            program_path_obj = repo_root / program_path_obj

    # --- 2. Load configuration ---
    try:
        cfg = load_config()
    except Exception as exc:
        return {
            "final_score": 0.0,
            "valid": False,
            "failure_reason": f"Config load failed: {exc}",
            "sub_scores": {},
            "weighted_scores": {},
            "total_weight": 0.0,
        }

    template_seq: str = cfg["template"]["sequence"]
    amp_start: int = cfg["amplicon"]["start_index"]
    amp_end: int = cfg["amplicon"]["end_index"]

    # --- 3. Load submission ---
    if program_path_obj.suffix == ".json":
        with open(program_path_obj) as sf:
            submission = json.load(sf)
    else:
        # Run candidate script and capture submission.json
        import subprocess
        import tempfile
        python = kernel_python or sys.executable
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                script_result = subprocess.run(
                    [python, str(program_path_obj)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=tmpdir,
                )
                if script_result.returncode != 0:
                    return {
                        "final_score": 0.0,
                        "valid": False,
                        "failure_reason": f"Candidate script failed: {script_result.stderr.strip()}",
                        "sub_scores": {},
                        "weighted_scores": {},
                        "total_weight": 0.0,
                    }
                # Parse JSON from stdout
                try:
                    submission = json.loads(script_result.stdout)
                except json.JSONDecodeError:
                    submission_path_candidate = tmp_path / "submission.json"
                    if submission_path_candidate.exists():
                        with open(submission_path_candidate) as sf:
                            submission = json.load(sf)
                    else:
                        return {
                            "final_score": 0.0,
                            "valid": False,
                            "failure_reason": "Candidate produced no parseable submission JSON",
                            "sub_scores": {},
                            "weighted_scores": {},
                            "total_weight": 0.0,
                        }
        except subprocess.TimeoutExpired:
            return {
                "final_score": 0.0,
                "valid": False,
                "failure_reason": "Candidate script timed out (120s)",
                "sub_scores": {},
                "weighted_scores": {},
                "total_weight": 0.0,
            }
        except Exception as exc:
            return {
                "final_score": 0.0,
                "valid": False,
                "failure_reason": f"Candidate execution error: {exc}",
                "sub_scores": {},
                "weighted_scores": {},
                "total_weight": 0.0,
            }

    # --- 4. Parse submission ---
    fwd: str = submission.get("forward_primer", submission.get("fwd", ""))
    rev: str = submission.get("reverse_primer", submission.get("rev", ""))
    if not fwd or not rev:
        return {
            "final_score": 0.0,
            "valid": False,
            "failure_reason": "Submission missing forward_primer or reverse_primer",
            "sub_scores": {},
            "weighted_scores": {},
            "total_weight": 0.0,
        }

    # --- 5. Compute product length (once) ---
    alignment = align_primers(fwd, rev, template_seq, amp_start, amp_end)
    if not alignment["perfect_match"]:
        pass  # alignment failed; hard gate will catch it
    rev_rc_len = len(reverse_complement(rev))
    if alignment["fwd_start"] != -1 and alignment["rev_end"] != -1:
        product_length = alignment["rev_end"] + rev_rc_len - alignment["fwd_start"]
    else:
        product_length = 0

    # --- 6. Run hard validation gates ---
    gates_ok = run_hard_gates(
        fwd, rev, cfg,
        template_seq, amp_start, amp_end,
    )
    if not gates_ok:
        return {
            "final_score": 0.0,
            "valid": False,
            "failure_reason": "Hard validation gate(s) failed",
            "sub_scores": {},
            "weighted_scores": {},
            "total_weight": 0.0,
        }

    # --- 7. Compute score breakdown ---
    breakdown = compute_score_breakdown(fwd, rev, cfg, product_length)

    return {
        "final_score": breakdown["final_score"],
        "valid": True,
        "failure_reason": "",
        "sub_scores": breakdown["sub_scores"],
        "weighted_scores": breakdown["weighted_scores"],
        "total_weight": breakdown["total_weight"],
    }

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  CLI  (Spec §7.2)                                                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def main() -> None:
    """Command-line entry point for standalone evaluation.

    Supports two invocation modes:

    - ``python verification/evaluator.py --submission submission.json``
    - ``python verification/evaluator.py scripts/init.py``

    Spec
    ----
    §7.2 — CLI invocation.
    """
    parser = argparse.ArgumentParser(
        description="PCR Primer Design Optimization — Evaluator",
    )
    parser.add_argument(
        "candidate",
        nargs="?",
        help="Path to a candidate Python script (e.g. scripts/init.py).",
    )
    parser.add_argument(
        "--submission",
        type=str,
        default=None,
        help="Path to an existing submission.json.",
    )
    parser.add_argument(
        "--metrics-out",
        type=str,
        default=None,
        help="Optional path to write metrics JSON (used by frontier_eval).",
    )
    args = parser.parse_args()

    # Determine the input: --submission takes priority, then positional arg.
    if args.submission is not None:
        target: str = args.submission
    elif args.candidate is not None:
        target = args.candidate
    else:
        parser.print_help()
        sys.exit(1)

    result = evaluate(target)

    # Pretty-print to stdout.
    print(json.dumps(result, indent=2))

    # Write metrics file if requested.
    if args.metrics_out is not None:
        metrics_path = Path(args.metrics_out)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with open(metrics_path, "w", encoding="utf-8") as mf:
            json.dump(result, mf, indent=2)

if __name__ == "__main__":
    main()
