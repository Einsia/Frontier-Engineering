"""Baseline solution for PCR Primer Design Optimization.

This module implements a genetic-algorithm-based primer designer that
searches for optimal forward/reverse primer pairs given a template
sequence and thermodynamic constraints defined in primer_config.json.

The entrypoint `design_primers()` returns:
    {"forward_primer": "...", "reverse_primer": "..."}
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
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
# Thermodynamic helpers
# ---------------------------------------------------------------------------

_COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}


def reverse_complement(seq: str) -> str:
    return "".join(_COMPLEMENT[b] for b in reversed(seq))


def _complement(seq: str) -> str:
    """Return the complement of a DNA sequence (no reversal)."""
    return "".join(_COMPLEMENT[b] for b in seq)


def nearest_neighbor_delta(
    seq: str,
    enthalpy: dict[str, float],
    entropy: dict[str, float],
) -> tuple[float, float]:
    dh, ds = 0.0, 0.0
    for i in range(len(seq) - 1):
        dimer = seq[i : i + 2]
        pair_key = dimer + "/" + _complement(dimer)
        if pair_key not in enthalpy:
            pair_key = reverse_complement(dimer) + "/" + reverse_complement(_complement(dimer))
        dh += enthalpy.get(pair_key, 0.0)
        ds += entropy.get(pair_key, 0.0)
    dh += 0.2
    ds += -5.7
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
    dh, ds = nearest_neighbor_delta(seq, enthalpy, entropy)
    r = 1.987
    monovalent_eff = monovalent + 3.7 * math.sqrt(max(0, divalent - dntp))
    salt_correction = 0.368 * (len(seq) - 1) * math.log(monovalent_eff / 1000.0)
    tm = (1000.0 * dh) / (ds + r * math.log(dna_conc / 1e9) + salt_correction) - 273.15
    return round(tm, 2)


def compute_gc_content(seq: str) -> float:
    if not seq:
        return 0.0
    gc = sum(1 for b in seq.upper() if b in "GC")
    return 100.0 * gc / len(seq)


def compute_self_complementarity(seq: str) -> int:
    """Maximum 3''-end-biased complementarity with the primer itself."""
    rc = reverse_complement(seq)
    seq_u, rc_u = seq.upper(), rc.upper()
    best = 0
    for i in range(len(seq_u) - 2):
        for j in range(i + 3, len(seq_u) + 1):
            sub = seq_u[i:j]
            if sub in rc_u:
                best = max(best, len(sub))
    return best


def compute_pair_complementarity(fwd: str, rev: str) -> int:
    """Maximum complementarity between forward and reverse primers (3''-end biased)."""
    fwd_u, rev_u = fwd.upper(), rev.upper()
    rev_rc = reverse_complement(rev).upper()
    fwd_rc = reverse_complement(fwd).upper()
    best = 0
    for i in range(len(fwd_u) - 2):
        for j in range(i + 3, len(fwd_u) + 1):
            sub = fwd_u[i:j]
            if sub in rev_rc:
                best = max(best, len(sub))
    for i in range(len(rev_u) - 2):
        for j in range(i + 3, len(rev_u) + 1):
            sub = rev_u[i:j]
            if sub in fwd_rc:
                best = max(best, len(sub))
    return best


def count_repeats(seq: str) -> int:
    s = seq.upper()
    best = 0
    for i in range(len(s)):
        for j in range(i + 1, len(s)):
            sub = s[i:j]
            if s.count(sub) >= 2:
                best = max(best, len(sub))
    return best


def compute_hairpin_stem(seq: str) -> int:
    """Estimate maximum hairpin stem length (capped at 8 bp)."""
    rc = reverse_complement(seq)
    best = 0
    max_cap = min(8, len(seq) // 2)
    for offset in range(1, len(seq)):
        fwd_part = seq[offset:]
        rc_part = rc[: len(seq) - offset]
        max_k = min(len(fwd_part), len(rc_part), max_cap)
        for k in range(3, max_k + 1):
            if fwd_part[:k] == reverse_complement(rc_part[:k]):
                best = max(best, k)
    return best


# ---------------------------------------------------------------------------
# Scoring function (same logic as scripts/init.py)
# ---------------------------------------------------------------------------

def score_primer_pair(fwd: str, rev: str, cfg: dict[str, Any]) -> dict[str, Any]:
    weights = cfg["scoring_weights"]
    cons = cfg["constraints"]
    thermo = cfg["thermodynamic"]
    nn = thermo["nearest_neighbor_params"]
    enh = nn["enthalpy_kcal"]
    ent = nn["entropy_cal"]

    tm_fwd = compute_melting_temperature(
        fwd, thermo["monovalent_cation_concentration"],
        thermo["divalent_cation_concentration"],
        thermo["dntp_concentration"], thermo["dna_concentration"], enh, ent,
    )
    tm_rev = compute_melting_temperature(
        rev, thermo["monovalent_cation_concentration"],
        thermo["divalent_cation_concentration"],
        thermo["dntp_concentration"], thermo["dna_concentration"], enh, ent,
    )
    tm_optimal = cons["melting_temperature"]["optimal"]
    tm_diff = abs(tm_fwd - tm_rev)
    tm_score = max(0, 100 - 10 * abs(tm_fwd - tm_optimal) - 10 * abs(tm_rev - tm_optimal) - 15 * tm_diff)

    gc_fwd = compute_gc_content(fwd)
    gc_rev = compute_gc_content(rev)
    gc_center = (cons["gc_content"]["min"] + cons["gc_content"]["max"]) / 2.0
    gc_score = max(0, 100 - 5 * abs(gc_fwd - gc_center) - 5 * abs(gc_rev - gc_center))

    len_fwd, len_rev = len(fwd), len(rev)
    len_center = (cons["primer_length"]["min"] + cons["primer_length"]["max"]) / 2.0
    len_score = max(0, 100 - 10 * abs(len_fwd - len_center) - 10 * abs(len_rev - len_center))

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

    self_comp_fwd = compute_self_complementarity(fwd)
    self_comp_rev = compute_self_complementarity(rev)
    self_comp_score = max(0, 100 - 20 * (self_comp_fwd + self_comp_rev))

    pair_comp = compute_pair_complementarity(fwd, rev)
    pair_comp_score = max(0, 100 - 20 * pair_comp)

    rep_fwd = count_repeats(fwd)
    rep_rev = count_repeats(rev)
    repeat_score = max(0, 100 - 15 * (rep_fwd + rep_rev))

    hp_fwd = compute_hairpin_stem(fwd)
    hp_rev = compute_hairpin_stem(rev)
    hp_limit = cons["max_hairpin_stem"]
    hp_score = 100.0
    if hp_fwd > hp_limit:
        hp_score -= 20 * (hp_fwd - hp_limit)
    if hp_rev > hp_limit:
        hp_score -= 20 * (hp_rev - hp_limit)
    hp_score = max(0, hp_score)

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

    total = (
        weights["tm_score"] * tm_score
        + weights["gc_content_score"] * gc_score
        + weights["length_score"] * len_score
        + weights["gc_clamp_score"] * gc_clamp_score
        + weights["self_complementarity_score"] * self_comp_score
        + weights["pair_complementarity_score"] * pair_comp_score
        + weights["repeat_score"] * repeat_score
        + weights["hairpin_score"] * hp_score
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
# Genetic Algorithm Primer Designer
# ---------------------------------------------------------------------------

def _candidate_from_bounds(
    template: str,
    amp_start: int,
    amp_end: int,
    min_len: int,
    max_len: int,
) -> tuple[str, str]:
    """Generate a random primer pair from the target region bounds."""
    fwd_start = amp_start
    fwd_end = amp_end
    fwd_len = random.randint(min_len, min(max_len, fwd_end - fwd_start))
    fwd = template[fwd_start : fwd_start + fwd_len]

    rev_start = max(amp_start, amp_end - max_len + 1)
    rev_end = amp_end + 1
    rev_len = random.randint(min_len, min(max_len, rev_end - rev_start))
    rev_seq = template[rev_end - rev_len : rev_end]
    rev = reverse_complement(rev_seq)
    return fwd, rev


def _mutate(
    fwd: str,
    rev: str,
    template: str,
    amp_start: int,
    amp_end: int,
    min_len: int,
    max_len: int,
    mutation_rate: float,
) -> tuple[str, str]:
    """Mutate a primer pair by shifting, lengthening, or shortening."""
    bases = ["A", "T", "C", "G"]
    new_fwd = list(fwd)
    new_rev = list(rev)

    # Point mutations
    for i in range(len(new_fwd)):
        if random.random() < mutation_rate:
            new_fwd[i] = random.choice(bases)
    for i in range(len(new_rev)):
        if random.random() < mutation_rate:
            new_rev[i] = random.choice(bases)

    # Length changes
    if random.random() < 0.1 and len(new_fwd) < max_len:
        pos = amp_start + len(new_fwd)
        if pos < amp_end:
            new_fwd.append(template[pos])
    if random.random() < 0.1 and len(new_fwd) > min_len:
        new_fwd.pop()
    if random.random() < 0.1 and len(new_rev) < max_len:
        pos = amp_end - len(new_rev)
        if pos >= amp_start:
            new_rev.append("".join(_COMPLEMENT[b] for b in reversed(template[pos - 1 : pos])))
    if random.random() < 0.1 and len(new_rev) > min_len:
        new_rev.pop()

    return "".join(new_fwd), "".join(new_rev)


def _crossover(
    p1_fwd: str, p1_rev: str,
    p2_fwd: str, p2_rev: str,
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Single-point crossover between two primer pairs."""
    if len(p1_fwd) < 2 or len(p2_fwd) < 2 or len(p1_rev) < 2 or len(p2_rev) < 2:
        return (p1_fwd, p1_rev), (p2_fwd, p2_rev)

    pt_fwd = random.randint(1, min(len(p1_fwd), len(p2_fwd)) - 1)
    pt_rev = random.randint(1, min(len(p1_rev), len(p2_rev)) - 1)

    c1_fwd = p1_fwd[:pt_fwd] + p2_fwd[pt_fwd:]
    c1_rev = p1_rev[:pt_rev] + p2_rev[pt_rev:]
    c2_fwd = p2_fwd[:pt_fwd] + p1_fwd[pt_fwd:]
    c2_rev = p2_rev[:pt_rev] + p1_rev[pt_rev:]

    return (c1_fwd, c1_rev), (c2_fwd, c2_rev)


def _tournament_select(
    population: list[tuple[str, str]],
    scores: list[float],
    k: int,
) -> tuple[str, str]:
    """Select an individual via tournament selection."""
    best_idx = random.randrange(len(population))
    for _ in range(k - 1):
        idx = random.randrange(len(population))
        if scores[idx] > scores[best_idx]:
            best_idx = idx
    return population[best_idx]


def design_primers() -> dict[str, str]:
    """Design PCR primers using a genetic algorithm.

    Returns:
        dict with keys "forward_primer" and "reverse_primer".
    """
    cfg = load_config()
    random.seed(42)
    template = cfg["template"]["sequence"]
    amp_start = cfg["amplicon"]["start_index"]
    amp_end = cfg["amplicon"]["end_index"]
    cons = cfg["constraints"]
    opt = cfg["optimization"]

    min_len = cons["primer_length"]["min"]
    max_len = cons["primer_length"]["max"]
    pop_size = opt["population_size"]
    generations = opt["generations"]
    mutation_rate = opt["mutation_rate"]
    crossover_rate = opt["crossover_rate"]
    tournament_k = opt["tournament_size"]
    elite_count = max(1, int(pop_size * opt["elite_ratio"]))

    # Initialize population
    population: list[tuple[str, str]] = []
    for _ in range(pop_size):
        fwd, rev = _candidate_from_bounds(template, amp_start, amp_end, min_len, max_len)
        population.append((fwd, rev))

    best_pair = population[0]
    best_score = -float("inf")

    for gen in range(generations):
        scores = []
        for fwd, rev in population:
            report = score_primer_pair(fwd, rev, cfg)
            if report["feasible"]:
                scores.append(report["total_score"])
            else:
                scores.append(-1000.0)  # heavy penalty for infeasible

        # Track best
        gen_best = max(scores)
        gen_best_idx = scores.index(gen_best)
        if gen_best > best_score:
            best_score = gen_best
            best_pair = population[gen_best_idx]

        if gen % 10 == 0 or gen == generations - 1:
            print(f"  Gen {gen:3d}: best score = {best_score:.2f}")

        # Elitism
        ranked = sorted(zip(population, scores), key=lambda x: x[1], reverse=True)
        next_pop = [pair for pair, _ in ranked[:elite_count]]

        # Generate offspring
        while len(next_pop) < pop_size:
            p1 = _tournament_select(population, scores, tournament_k)
            p2 = _tournament_select(population, scores, tournament_k)

            if random.random() < crossover_rate:
                c1, c2 = _crossover(p1[0], p1[1], p2[0], p2[1])
                offspring = [c1, c2]
            else:
                offspring = [p1, p2]

            for fwd, rev in offspring:
                fwd, rev = _mutate(fwd, rev, template, amp_start, amp_end, min_len, max_len, mutation_rate)
                next_pop.append((fwd, rev))
                if len(next_pop) >= pop_size:
                    break

        population = next_pop[:pop_size]

    fwd, rev = best_pair
    print(f"\nBest forward:  {fwd}")
    print(f"Best reverse:  {rev}")
    final_report = score_primer_pair(fwd, rev, cfg)
    print(f"Score:         {final_report['total_score']}")
    print(f"Feasible:      {final_report['feasible']}")
    print(f"Tm fwd/rev:    {final_report['tm_fwd']:.1f}C / {final_report['tm_rev']:.1f}C")
    print(f"GC fwd/rev:    {final_report['gc_fwd']:.1f}% / {final_report['gc_rev']:.1f}%")

    return {"forward_primer": fwd, "reverse_primer": rev}


if __name__ == "__main__":
    result = design_primers()
    with open("submission.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("Submission written to submission.json")
