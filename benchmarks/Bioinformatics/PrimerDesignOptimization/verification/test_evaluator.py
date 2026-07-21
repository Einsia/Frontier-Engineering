#!/usr/bin/env python3
"""Comprehensive test suite for PrimerDesignOptimization evaluator."""
from __future__ import annotations
import json, math, os, sys, unittest
from pathlib import Path
BENCHMARK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BENCHMARK_ROOT))
from verification import evaluator as ev
def _load_cfg():
    return ev.load_config()

class TestHardGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = _load_cfg()
        cls.template = cls.cfg["template"]["sequence"]
        cls.amp_start = cls.cfg["amplicon"]["start_index"]
        cls.amp_end = cls.cfg["amplicon"]["end_index"]
        cls.valid_fwd = "CAAAGCGATTGTTGGGATTGTACT"
        cls.valid_rev = "TTAATTCATTAGCCCGACGTTACC"

    def test_charset_valid(self):
        self.assertTrue(ev.validate_charset("ATCG","ATCG"))
        self.assertTrue(ev.validate_charset("atcg","atcg"))

    def test_charset_invalid(self):
        self.assertFalse(ev.validate_charset("ATCGX","ATCG"))
        self.assertFalse(ev.validate_charset("","ATCG"))

    def test_length_valid(self):
        self.assertTrue(ev.validate_length("A"*20,"T"*20,self.cfg))
        self.assertTrue(ev.validate_length("A"*25,"T"*25,self.cfg))

    def test_length_too_short(self):
        self.assertFalse(ev.validate_length("A"*17,"T"*20,self.cfg))
        self.assertFalse(ev.validate_length("A"*20,"T"*17,self.cfg))

    def test_length_too_long(self):
        self.assertFalse(ev.validate_length("A"*26,"T"*20,self.cfg))
        self.assertFalse(ev.validate_length("A"*20,"T"*26,self.cfg))

    def test_gc_valid(self):
        self.assertTrue(ev.validate_gc_content("ACACACACACACACACACAC","ACACACACACACACACACAC",self.cfg))

    def test_gc_too_low(self):
        self.assertFalse(ev.validate_gc_content("A"*20,"ACACACACACACACACACAC",self.cfg))

    def test_gc_too_high(self):
        self.assertFalse(ev.validate_gc_content("G"*20,"ACACACACACACACACACAC",self.cfg))

    def test_tm_valid(self):
        self.assertTrue(ev.validate_tm(self.valid_fwd,self.valid_rev,self.cfg))

    def test_tm_too_low(self):
        self.assertFalse(ev.validate_tm("A"*20,"A"*20,self.cfg))

    def test_gc_clamp_valid(self):
        self.assertTrue(ev.validate_gc_clamp("AAAAAAAAAAAAAAACCC","TTTTTTTTTTTTTTTGGG",self.cfg))

    def test_gc_clamp_invalid(self):
        self.assertFalse(ev.validate_gc_clamp("A"*19,"T"*19,self.cfg))

    def test_self_comp_valid(self):
        self.assertTrue(ev.validate_self_complementarity("AAAACCCCTTTTGGGG","TTTTTTTTTTTTTTTT",self.cfg))

    def test_self_comp_invalid(self):
        self.assertFalse(ev.validate_self_complementarity("A"*12,"T"*12,self.cfg))

    def test_hairpin_valid(self):
        self.assertTrue(ev.validate_hairpin("ACGTACGTACGT","TTTTTTTTTTTT",self.cfg))

    def test_hairpin_invalid(self):
        self.assertFalse(ev.validate_hairpin("AAAAAAAAACCCGGGTTTTTTTTT","A"*24,self.cfg))

    def test_mono_run_valid(self):
        self.assertTrue(ev.validate_mononucleotide_run("ACGTACGTACGT","ACGTACGTACGT",self.cfg))

    def test_mono_run_invalid(self):
        self.assertFalse(ev.validate_mononucleotide_run("A"*14,"ACGTACGTACGT",self.cfg))

    def test_alignment_valid(self):
        self.assertTrue(ev.validate_alignment(self.valid_fwd,self.valid_rev,self.template,self.amp_start,self.amp_end))

    def test_alignment_invalid(self):
        self.assertFalse(ev.validate_alignment("A"*20,"T"*20,self.template,self.amp_start,self.amp_end))

    def test_prod_len_valid(self):
        self.assertTrue(ev.validate_product_length(self.valid_fwd,self.valid_rev,self.template))

    def test_prod_len_invalid(self):
        self.assertFalse(ev.validate_product_length("A"*20,"A"*20,self.template))

    def test_run_hard_gates_valid(self):
        self.assertTrue(ev.run_hard_gates(self.valid_fwd,self.valid_rev,self.cfg,self.template,self.amp_start,self.amp_end))

    def test_run_hard_gates_invalid(self):
        self.assertFalse(ev.run_hard_gates("ATCGX","ATCG",self.cfg,self.template,self.amp_start,self.amp_end))

class TestMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = _load_cfg()
        cls.valid_fwd = "CAAAGCGATTGTTGGGATTGTACT"
        cls.valid_rev = "TTAATTCATTAGCCCGACGTTACC"

    def _check(self, name, func, *args, **kw):
        r = func(*args, **kw)
        self.assertIsInstance(r, float)
        self.assertFalse(math.isnan(r), f"{name} NaN")
        self.assertFalse(math.isinf(r), f"{name} Inf")
        self.assertGreaterEqual(r, 0.0, f"{name} < 0")
        self.assertLessEqual(r, 1.0, f"{name} > 1")
        return r

    def test_length_score(self):
        self._check("length_score", ev.length_score, "A"*20, "T"*20, self.cfg)

    def test_gc_content_score(self):
        self._check("gc_content_score", ev.gc_content_score, "ACACACACACACACACACAC","ACACACACACACACACACAC",self.cfg)

    def test_tm_score(self):
        self._check("tm_score", ev.tm_score, self.valid_fwd, self.valid_rev, self.cfg)

    def test_gc_clamp_score(self):
        self._check("gc_clamp_score", ev.gc_clamp_score, self.valid_fwd, self.valid_rev, self.cfg)

    def test_self_comp_score(self):
        self._check("self_complementarity_score", ev.self_complementarity_score, self.valid_fwd, self.valid_rev, self.cfg)

    def test_pair_comp_score(self):
        self._check("pair_complementarity_score", ev.pair_complementarity_score, self.valid_fwd, self.valid_rev, self.cfg)

    def test_repeat_score(self):
        self._check("repeat_score", ev.repeat_score, self.valid_fwd, self.valid_rev, self.cfg)

    def test_hairpin_score(self):
        self._check("hairpin_score", ev.hairpin_score, self.valid_fwd, self.valid_rev, self.cfg)

    def test_mono_run_score(self):
        self._check("mononucleotide_run_score", ev.mononucleotide_run_score, self.valid_fwd, self.valid_rev, self.cfg)

    def test_prod_len_score(self):
        self._check("product_length_score", ev.product_length_score, self.valid_fwd, self.valid_rev, self.cfg, 80)

class TestBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = _load_cfg()
        cls.benchmark_root = Path(__file__).resolve().parent.parent

    def test_baseline_eval(self):
        r = ev.evaluate(str(self.benchmark_root/"scripts"/"init.py"))
        self.assertIn("final_score", r)
        self.assertIn("valid", r)
        self.assertIn("failure_reason", r)
        self.assertIn("sub_scores", r)
        self.assertIn("weighted_scores", r)
        self.assertIn("total_weight", r)
        self.assertTrue(r["valid"], f"Baseline failed: {r['failure_reason']}")
        self.assertGreaterEqual(r["final_score"], 0.0)
        self.assertLessEqual(r["final_score"], 1.0)
        expected = ["length_score","gc_content_score","tm_score","gc_clamp_score","self_complementarity_score","pair_complementarity_score","repeat_score","hairpin_score","mononucleotide_run_score","product_length_score"]
        for m in expected:
            self.assertIn(m, r["sub_scores"])
            self.assertIn(m, r["weighted_scores"])
            self.assertGreaterEqual(r["sub_scores"][m], 0.0)
            self.assertLessEqual(r["sub_scores"][m], 1.0)
        self.assertAlmostEqual(r["total_weight"], sum(self.cfg["scoring_weights"].values()), places=4)

    def test_determinism(self):
        candidate = str(self.benchmark_root/"scripts"/"init.py")
        r1 = ev.evaluate(candidate)
        r2 = ev.evaluate(candidate)
        r3 = ev.evaluate(candidate)
        self.assertEqual(r1["final_score"], r2["final_score"])
        self.assertEqual(r1["final_score"], r3["final_score"])
        self.assertEqual(r1["sub_scores"], r2["sub_scores"])

class TestHiddenTemplates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.benchmark_root = Path(__file__).resolve().parent.parent

    def test_hidden_loaded(self):
        hidden = ev._load_hidden_templates()
        self.assertGreater(len(hidden), 0)
        for ht in hidden:
            self.assertIn("template", ht)
            self.assertIn("amplicon", ht)
            self.assertGreater(len(ht["template"]["sequence"]), 0)

    def test_hidden_config(self):
        cfg = _load_cfg()
        hidden = ev._load_hidden_templates()
        if not hidden:
            self.skipTest("no hidden templates")
        for ht in hidden:
            hcfg = ev._make_hidden_config(ht, cfg)
            self.assertEqual(hcfg["template"]["sequence"], ht["template"]["sequence"])

class TestUtilities(unittest.TestCase):
    def test_rc(self):
        self.assertEqual(ev.reverse_complement("ATCG"), "CGAT")
        self.assertEqual(ev.reverse_complement(""), "")

    def test_canonical(self):
        self.assertEqual(ev.canonical_pair_key("AA"), "AA/TT")
        self.assertEqual(ev.canonical_pair_key("TT"), "TT/AA")

    def test_valid_dna(self):
        self.assertTrue(ev.is_valid_dna("ATCG"))
        self.assertFalse(ev.is_valid_dna("ATCGX"))

    def test_gc_content(self):
        self.assertAlmostEqual(ev.compute_gc_content("ATCG"), 50.0)
        self.assertAlmostEqual(ev.compute_gc_content("AAAA"), 0.0)
        self.assertAlmostEqual(ev.compute_gc_content("GGGG"), 100.0)

    def test_tm_deterministic(self):
        cfg = _load_cfg()
        self.assertAlmostEqual(ev.compute_tm("CGTCCACAAGAAAGCTTTCC",cfg), ev.compute_tm("CGTCCACAAGAAAGCTTTCC",cfg), places=6)

class TestScoreBreakdown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = _load_cfg()
        cls.valid_fwd = "CAAAGCGATTGTTGGGATTGTACT"
        cls.valid_rev = "TTAATTCATTAGCCCGACGTTACC"

    def test_structure(self):
        bd = ev.compute_score_breakdown(self.valid_fwd, self.valid_rev, self.cfg, 80)
        self.assertIn("final_score", bd)
        self.assertIn("sub_scores", bd)
        self.assertIn("weighted_scores", bd)
        self.assertIn("total_weight", bd)
        self.assertNotIn("valid", bd)
        self.assertEqual(len(bd["sub_scores"]), 10)
        self.assertEqual(len(bd["weighted_scores"]), 10)

    def test_deterministic(self):
        bd1 = ev.compute_score_breakdown(self.valid_fwd, self.valid_rev, self.cfg, 80)
        bd2 = ev.compute_score_breakdown(self.valid_fwd, self.valid_rev, self.cfg, 80)
        self.assertEqual(bd1["final_score"], bd2["final_score"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
