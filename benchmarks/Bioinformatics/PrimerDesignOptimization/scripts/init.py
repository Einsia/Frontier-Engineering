"""Baseline PCR primer design optimizer.

DO NOT MODIFY: load_config(), score_primer_pair(), compute_melting_temperature(),
    compute_gc_content(), evaluate_complementarity()
ALLOWED TO MODIFY: design_primers()

Outputs submission.json with designed forward and reverse primers.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# DO NOT MODIFY — Configuration loader
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Load primer_config.json from references/."""
    candidates = [
        Path(__file__).resolve().parent / "references" / "primer_config.json",
        Path(__file__).resolve().parent.parent / "references" / "primer_config.json",
    ]
    for p in candidates:
        if p.is_file():
            with p.open("r", encoding="utf-8-sig") as f:
                return json.load(f)
    raise FileNotFoundError("primer_config.json not found")


# ---------------------------------------------------------------------------
# DO NOT MODIFY — Thermodynamic helpers
# ---------------------------------------------------------------------------

def _reverse_complement(seq: str) -> str:
    """Return the reverse complement of a DNA sequence."""
    comp = {"A": "T", "T": "A", "C": "G", "G": "C"}
    return "".join(comp.get(base, base) for base in reversed(seq))


def _complement(seq: str) -> str:
    """Return the complement of a DNA sequence (no reversal)."""
    comp = {"A": "T", "T": "A", "C": "G", "G": "C"}
    return "".join(comp.get(base, base) for base in seq)


def _nearest_neighbor_delta(
    seq: str,
    enthalpy: dict[str, float],
    entropy: dict[str, float],
) -> tuple[float, float]:
    """Compute total enthalpy (kcal) and entropy (cal/K) for a DNA duplex."""
    dh = 0.0
    ds = 0.0
    for i in range(len(seq) - 1):
        dimer = seq[i : i + 2]
        pair_key = dimer + "/" + _complement(dimer)
        if pair_key not in enthalpy:
            # Try reverse-complement orientation for the pair
            pair_key = _reverse_complement(dimer) + "/" + _reverse_complement(_complement(dimer))
        dh += enthalpy.get(pair_key, 0.0)
        ds += entropy.get(pair_key, 0.0)
    # Initiation parameters (per SantaLucia 1998)
    dh += 0.2
    ds += -5.7
    # Terminal AT penalty
    if seq[0] in "AT":
        dh += 2.3
        ds += 4.1
    if seq[-1] in "AT":
        dh += 2.3
        ds += 4.1
    return dh, ds


def compute_melting_temperature(
    seq: str,
    monovalent: float,
    divalent: float,
    dntp: float,
    dna_conc: float,
    enthalpy: dict[str, float],
    entropy: dict[str, float],
) -> float:
    """Compute melting temperature (Celsius) using nearest-neighbor model."""
    dh, ds = _nearest_neighbor_delta(seq, enthalpy, entropy)
    r = 1.987  # Cal / (mol * K)
    # SantaLucia salt correction
    monovalent_eff = monovalent + 3.7 * math.sqrt(max(0.0, divalent - dntp))
    salt_correction = 0.368 * (len(seq) - 1) * math.log(monovalent_eff / 1000.0, math.e)
    tm = (1000.0 * dh) / (ds + r * math.log(dna_conc / 1e9, math.e) + salt_correction) - 273.15
    return round(tm, 2)


def compute_gc_content(seq: str) -> float:
    """Compute GC content percentage."""
    if not seq:
        return 0.0
    gc = sum(1 for base in seq.upper() if base in "GC")
    return 100.0 * gc / len(seq)


def compute_self_complementarity(seq: str) -> int:
    """Maximum contiguous 3''-end complementarity with the primer itself.
    
    Weighted toward 3''-end matches (critical for primer-dimer formation).
    """
    rc = _reverse_complement(seq)
    seq_u = seq.upper()
    rc_u = rc.upper()
    best = 0
    # Check complementarity starting from 3'' end of seq (i.e., seq suffix vs rc)
    for i in range(len(seq_u) - 2):
        for j in range(i + 3, len(seq_u) + 1):
            sub = seq_u[i:j]
            if sub in rc_u:
                best = max(best, len(sub))
    return best


def compute_pair_complementarity(fwd: str, rev: str) -> int:
    """Maximum contiguous complementarity between forward and reverse primers.
    
    Checks fwd 3''-end complementarity against rev and vice versa.
    """
    fwd_u = fwd.upper()
    rev_u = rev.upper()
    rev_rc = _reverse_complement(rev)
    fwd_rc = _reverse_complement(fwd)
    best = 0
    # Fwd region vs rev rc
    for i in range(len(fwd_u) - 2):
        for j in range(i + 3, len(fwd_u) + 1):
            sub = fwd_u[i:j]
            if sub in rev_rc:
                best = max(best, len(sub))
    # Rev region vs fwd rc  
    for i in range(len(rev_u) - 2):
        for j in range(i + 3, len(rev_u) + 1):
            sub = rev_u[i:j]
            if sub in fwd_rc:
                best = max(best, len(sub))
    return best


def count_repeats(seq: str) -> int:
    """Maximum length of any repeated substring in the primer."""
    seq_upper = seq.upper()
    max_len = 0
    for i in range(len(seq_upper)):
        for j in range(i + 1, len(seq_upper) + 1):
            sub = seq_upper[i:j]
            if j + len(sub) <= len(seq_upper) and sub in seq_upper[j:]:
                # Count total occurrences
                count = 0
                pos = 0
                while True:
                    pos = seq_upper.find(sub, pos)
                    if pos == -1:
                        break
                    count += 1
                    pos += 1
                if count >= 2:
                    max_len = max(max_len, len(sub))
    return max_len


def compute_hairpin_stem(seq: str) -> int:
    """Estimate maximum hairpin stem length (capped at 8 bp).
    
    A hairpin requires a stem of complementary bases with a loop (>=3 bases).
    Returns the maximum stem length found, capped at 8 bp.
    """
    rc = _reverse_complement(seq)
    max_stem = 0
    max_cap = min(8, len(seq) // 2)
    for i in range(1, len(seq)):
        fwd_part = seq[i:]
        rc_part = rc[: len(seq) - i]
        max_k = min(len(fwd_part), len(rc_part), max_cap)
        for k in range(3, max_k + 1):
            sub_fwd = fwd_part[:k]
            sub_rc = rc_part[:k]
            if sub_fwd == _reverse_complement(sub_rc):
                max_stem = max(max_stem, k)
    return max_stem


# ---------------------------------------------------------------------------
# DO NOT MODIFY — Scoring
# ---------------------------------------------------------------------------

def score_primer_pair(fwd: str, rev: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Score a forward/reverse primer pair.

    Returns dict with individual metrics and weighted total score.
    Higher score is better.
    """
    template = cfg["template"]["sequence"]
    weights = cfg["scoring_weights"]
    cons = cfg["constraints"]
    thermo = cfg["thermodynamic"]
    nn = thermo["nearest_neighbor_params"]
    enh = nn["enthalpy_kcal"]
    ent = nn["entropy_cal"]

    # --- Melting temperature ---
    tm_fwd = compute_melting_temperature(
        fwd, thermo["monovalent_cation_concentration"],
        thermo["divalent_cation_concentration"],
        thermo["dntp_concentration"], thermo["dna_concentration"],
        enh, ent,
    )
    tm_rev = compute_melting_temperature(
        rev, thermo["monovalent_cation_concentration"],
        thermo["divalent_cation_concentration"],
        thermo["dntp_concentration"], thermo["dna_concentration"],
        enh, ent,
    )
    tm_optimal = cons["melting_temperature"]["optimal"]
    tm_diff = abs(tm_fwd - tm_rev)
    tm_score = max(0, 100 - 10 * abs(tm_fwd - tm_optimal) - 10 * abs(tm_rev - tm_optimal) - 15 * tm_diff)

    # --- GC content ---
    gc_fwd = compute_gc_content(fwd)
    gc_rev = compute_gc_content(rev)
    gc_center = (cons["gc_content"]["min"] + cons["gc_content"]["max"]) / 2.0
    gc_score = max(0, 100 - 5 * abs(gc_fwd - gc_center) - 5 * abs(gc_rev - gc_center))

    # --- Length ---
    len_fwd = len(fwd)
    len_rev = len(rev)
    len_center = (cons["primer_length"]["min"] + cons["primer_length"]["max"]) / 2.0
    len_score = max(0, 100 - 10 * abs(len_fwd - len_center) - 10 * abs(len_rev - len_center))

    # --- GC clamp (G/C in last 5 bases of 3'' end) ---
    gc_clamp_fwd = sum(1 for b in fwd[-5:].upper() if b in "GC")
    gc_clamp_rev = sum(1 for b in rev[-5:].upper() if b in "GC")
    gc_clamp_score = 100.0
    if cons["gc_clamp"]["required"]:
        if gc_clamp_fwd < 1:
            gc_clamp_score -= 25
        if gc_clamp_rev < 1:
            gc_clamp_score -= 25
        if gc_clamp_fwd > cons["gc_clamp"]["max_gc_in_last_5"]:
            gc_clamp_score -= 15
        if gc_clamp_rev > cons["gc_clamp"]["max_gc_in_last_5"]:
            gc_clamp_score -= 15

    # --- Self complementarity ---
    self_comp_fwd = compute_self_complementarity(fwd)
    self_comp_rev = compute_self_complementarity(rev)
    self_comp_score = max(
        0, 100 - 20 * (self_comp_fwd + self_comp_rev)
    )

    # --- Pair complementarity ---
    pair_comp = compute_pair_complementarity(fwd, rev)
    pair_comp_score = max(0, 100 - 20 * pair_comp)

    # --- Repeats ---
    rep_fwd = count_repeats(fwd)
    rep_rev = count_repeats(rev)
    repeat_score = max(0, 100 - 15 * (rep_fwd + rep_rev))

    # --- Hairpin ---
    hp_fwd = compute_hairpin_stem(fwd)
    hp_rev = compute_hairpin_stem(rev)
    hp_limit = cons["max_hairpin_stem"]
    hp_score = 100.0
    if hp_fwd > hp_limit:
        hp_score -= 20 * (hp_fwd - hp_limit)
    if hp_rev > hp_limit:
        hp_score -= 20 * (hp_rev - hp_limit)
    hp_score = max(0, hp_score)

    # Mononucleotide run score (homopolymer)
    mono_run_fwd = 0
    run = 1
    for i in range(1, len(fwd)):
        if fwd[i] == fwd[i - 1]:
            run += 1
        else:
            mono_run_fwd = max(mono_run_fwd, run)
            run = 1
    mono_run_fwd = max(mono_run_fwd, run)
    mono_run_rev = 0
    run = 1
    for i in range(1, len(rev)):
        if rev[i] == rev[i - 1]:
            run += 1
        else:
            mono_run_rev = max(mono_run_rev, run)
            run = 1
    mono_run_rev = max(mono_run_rev, run)
    mono_score_fwd = max(0, 100 - 25 * (mono_run_fwd - 1)) if mono_run_fwd > 1 else 100
    mono_score_rev = max(0, 100 - 25 * (mono_run_rev - 1)) if mono_run_rev > 1 else 100
    mono_run_score = (mono_score_fwd + mono_score_rev) // 2

    # Product length score
    template_seq = cfg["template"]["sequence"]
    amp_start = cfg["amplicon"]["start_index"]
    amp_end = cfg["amplicon"]["end_index"]
    _rc = {"A": "T", "T": "A", "C": "G", "G": "C"}
    fwd_pos = template_seq.find(fwd.upper(), max(0, amp_start - 5))
    rev_rc_str = "".join(_rc.get(b, b) for b in reversed(rev.upper()))
    rev_pos = template_seq.find(rev_rc_str, max(0, amp_end - len(rev_rc_str) - 5))
    if fwd_pos >= 0 and rev_pos >= 0:
        prod_len = rev_pos + len(rev_rc_str) - fwd_pos
        pref_min = cfg.get("product_length", {}).get("preferred_min", 80)
        pref_max = cfg.get("product_length", {}).get("preferred_max", 120)
        if pref_min <= prod_len <= pref_max:
            pl_score = 100
        elif prod_len < pref_min:
            pl_score = max(0, int(100 * prod_len / pref_min))
        else:
            max_tlen = len(template_seq)
            pl_score = max(0, int(100 * (max_tlen - prod_len) / (max_tlen - pref_max))) if max_tlen > pref_max else 0
    else:
        prod_len = 0
        pl_score = 0

    # --- Feasibility ---
    feasible = True
    violations: list[str] = []

    if not (cons["primer_length"]["min"] <= len_fwd <= cons["primer_length"]["max"]):
        violations.append(f"forward length {len_fwd} out of range")
        feasible = False
    if not (cons["primer_length"]["min"] <= len_rev <= cons["primer_length"]["max"]):
        violations.append(f"reverse length {len_rev} out of range")
        feasible = False
    if not (cons["gc_content"]["min"] <= gc_fwd <= cons["gc_content"]["max"]):
        violations.append(f"forward GC {gc_fwd:.1f}% out of range")
        feasible = False
    if not (cons["gc_content"]["min"] <= gc_rev <= cons["gc_content"]["max"]):
        violations.append(f"reverse GC {gc_rev:.1f}% out of range")
        feasible = False
    if not (cons["melting_temperature"]["min"] <= tm_fwd <= cons["melting_temperature"]["max"]):
        violations.append(f"forward Tm {tm_fwd:.1f}C out of range")
        feasible = False
    if not (cons["melting_temperature"]["min"] <= tm_rev <= cons["melting_temperature"]["max"]):
        violations.append(f"reverse Tm {tm_rev:.1f}C out of range")
        feasible = False
    if tm_diff > cons["tm_difference_max"]:
        violations.append(f"Tm difference {tm_diff:.1f}C exceeds max")
        feasible = False
    if self_comp_fwd > cons["self_complementarity_max"]:
        violations.append(f"forward self-complementarity {self_comp_fwd} exceeds max")
        feasible = False
    if self_comp_rev > cons["self_complementarity_max"]:
        violations.append(f"reverse self-complementarity {self_comp_rev} exceeds max")
        feasible = False
    if pair_comp > cons["pair_complementarity_max"]:
        violations.append(f"pair complementarity {pair_comp} exceeds max")
        feasible = False
    if hp_fwd > hp_limit:
        violations.append(f"forward hairpin stem {hp_fwd} bp exceeds limit")
        feasible = False
    if hp_rev > hp_limit:
        violations.append(f"reverse hairpin stem {hp_rev} bp exceeds limit")
        feasible = False

    # Total weighted score
    total = (
        weights["tm_score"] * tm_score
        + weights["gc_content_score"] * gc_score
        + weights["length_score"] * len_score
        + weights["gc_clamp_score"] * gc_clamp_score
        + weights["self_complementarity_score"] * self_comp_score
        + weights["pair_complementarity_score"] * pair_comp_score
        + weights["repeat_score"] * repeat_score
        + weights["hairpin_score"] * hp_score
        + weights.get("mononucleotide_run_score", 0.0) * mono_run_score
        + weights.get("product_length_score", 0.0) * pl_score
    )

    return {
        "total_score": round(total, 2),
        "feasible": feasible,
        "violations": violations,
        "tm_fwd": tm_fwd,
        "tm_rev": tm_rev,
        "tm_diff": round(tm_diff, 2),
        "gc_fwd": round(gc_fwd, 1),
        "gc_rev": round(gc_rev, 1),
        "len_fwd": len_fwd,
        "len_rev": len_rev,
        "gc_clamp_fwd": gc_clamp_fwd,
        "gc_clamp_rev": gc_clamp_rev,
        "self_comp_fwd": self_comp_fwd,
        "self_comp_rev": self_comp_rev,
        "pair_comp": pair_comp,
        "hp_fwd": hp_fwd,
        "hp_rev": hp_rev,
    }


# ---------------------------------------------------------------------------
# ALLOWED TO MODIFY — Primer design optimizer
# ---------------------------------------------------------------------------


# EVOLVE-BLOCK-START

def design_primers() -> dict[str, str]:
    """Design PCR primers for the target template.

    The default implementation takes the first 20 bp of each binding region
    as a simple baseline.

    Returns:
        dict with keys "forward_primer" and "reverse_primer".
    """
    cfg = load_config()
    template = cfg["template"]["sequence"]
    amp_start = cfg["amplicon"]["start_index"]
    amp_end = cfg["amplicon"]["end_index"]

    # Baseline: take first 20 bp of each binding region
    fwd = template[amp_start : amp_start + 20]
    rev_seq = template[amp_end - 19 : amp_end + 1]
    rev = "".join(
        {"A": "T", "T": "A", "C": "G", "G": "C"}.get(b, b)
        for b in reversed(rev_seq)
    )

    return {"forward_primer": fwd, "reverse_primer": rev}

# EVOLVE-BLOCK-END


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = design_primers()
    fwd, rev = result["forward_primer"], result["reverse_primer"]
    cfg = load_config()
    report = score_primer_pair(fwd, rev, cfg)
    print(f"Forward:  {fwd}")
    print(f"Reverse:  {rev}")
    print(f"Score:    {report['total_score']}")
    print(f"Feasible: {report['feasible']}")
    if report["violations"]:
        print(f"Violations: {report['violations']}")
    print(f"Tm fwd:   {report['tm_fwd']:.1f} C")
    print(f"Tm rev:   {report['tm_rev']:.1f} C")
    print(f"GC fwd:   {report['gc_fwd']:.1f}%")
    print(f"GC rev:   {report['gc_rev']:.1f}%")

    with open("submission.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("Submission written to submission.json")
